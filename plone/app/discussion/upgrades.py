from datetime import timezone
from plone import api
from plone.app.discussion.interfaces import IDiscussionSettings
from plone.registry.interfaces import IRegistry
from Products.CMFCore.utils import getToolByName
from Products.ZCatalog.ProgressHandler import ZLogHandler
from zope.component import getUtility

import logging


default_profile = "profile-plone.app.discussion:default"
logger = logging.getLogger("plone.app.discussion")


def update_registry(context):
    registry = getUtility(IRegistry)
    registry.registerInterface(IDiscussionSettings)


def update_rolemap(context):
    context.runImportStepFromProfile(default_profile, "rolemap")


def upgrade_comment_workflows_retain_current_workflow(context):
    # If the current comment workflow is the one_state_workflow, running our
    # import step will change it to comment_one_state_workflow.  This is good.
    # If it was anything else, we should restore this.  So get the original
    # chain.
    portal_type = "Discussion Item"
    wf_tool = getToolByName(context, "portal_workflow")
    orig_chain = list(wf_tool.getChainFor(portal_type))

    # Run the workflow step.  This sets the chain to
    # comment_one_state_workflow.
    context.runImportStepFromProfile(default_profile, "workflow")

    # Restore original workflow chain if needed.
    old_workflow = "one_state_workflow"
    if old_workflow not in orig_chain:
        # Restore the chain.  Probably comment_review_workflow.
        wf_tool.setChainForPortalTypes([portal_type], orig_chain)
    elif len(orig_chain) > 1:
        # This is strange, but I guess it could happen.
        if old_workflow in orig_chain:
            # Replace with new one.
            idx = orig_chain.index(old_workflow)
            orig_chain[idx] = "comment_one_state_workflow"
        # Restore the chain.
        wf_tool.setChainForPortalTypes([portal_type], orig_chain)


def upgrade_comment_workflows_apply_rolemapping(context):
    # Now go over the comments, update their role mappings, and reindex the
    # allowedRolesAndUsers index.
    return

def custom_freitag_upgrade(context):
    """Get the two upgrade steps from 5.2 to 6.0 and combine them

    These are the `set_timezone_on_dates` and
    `upgrade_comment_workflows_retain_current_workflow`.

    As both crawl over all comments, do it once and apply the changes of both
    upgrades in a single loop.

    As at der Freitag we have +500k comments,
    sprinkle some `transaction.commit()`
    otherwise when it finishes,
    it either runs out of memory or the transaction
    can not be pushed to the database.
    """
    import transaction

    portal_type = "Discussion Item"
    catalog = getToolByName(context, "portal_catalog")
    wf_tool = getToolByName(context, "portal_workflow")
    new_chain = list(wf_tool.getChainFor(portal_type))
    workflows = [wf_tool.getWorkflowById(wf_id) for wf_id in new_chain]

    # sort the brains so the most recent comments are updated first.
    # If the website is already live and running, those are probably the first
    # ones to be seen. Updating a +10 years old comment is probably something
    # no one would care for the ~4 hours this reindexing is happening
    brains = catalog.unrestrictedSearchResults(
        portal_type=portal_type,
        sort_on='effective',
        sort_order='reverse',
    )
    num_objects = len(brains)
    pghandler = ZLogHandler(1000)
    pghandler.init("Apply rolemap changes on comments", num_objects)
    for index, brain in enumerate(brains, 1):
        pghandler.report(index)
        try:
            comment = brain.getObject()
            for wf in workflows:
                wf.updateRoleMappingsFor(comment)
            comment.reindexObjectSecurity()
            if not comment.creation_date.tzinfo:
                creations += 1
                comment.creation_date = comment.creation_date.astimezone(timezone.utc)
            if not comment.modification_date.tzinfo:
                modifieds += 1
                comment.modification_date = comment.modification_date.astimezone(
                    timezone.utc
                )
        except (AttributeError, KeyError):
            logger.info(f"Could not reindex comment {brain.getURL()}")
        if index % 10000:
            transaction.commit()
            logger.info('Committing after %i comments indexed', index)
    pghandler.finish()


def upgrade_comment_workflows(context):
    upgrade_comment_workflows_retain_current_workflow(context)
    upgrade_comment_workflows_apply_rolemapping(context)


def add_js_to_plone_legacy(context):
    context.runImportStepFromProfile(default_profile, "plone.app.registry")


def extend_review_workflow(context):
    """Apply changes made to review workflow."""
    upgrade_comment_workflows_retain_current_workflow(context)


def set_timezone_on_dates(context):
    """Ensure timezone data is stored against all creation/modified dates"""
    return
    pc = api.portal.get_tool("portal_catalog")
    creations = 0
    modifieds = 0
    logger.info("Setting timezone information on comment dates")
    comments = pc.search({"portal_type": "Discussion Item"})

    num_objects = len(comments)
    pghandler = ZLogHandler(1000)
    pghandler.init("Set timezone on comments", num_objects)
    for index, cbrain in enumerate(comments, 1):
        pghandler.report(index)
        comment = cbrain.getObject()
        if not comment.creation_date.tzinfo:
            creations += 1
            comment.creation_date = comment.creation_date.astimezone(timezone.utc)
        if not comment.modification_date.tzinfo:
            modifieds += 1
            comment.modification_date = comment.modification_date.astimezone(
                timezone.utc
            )
    pghandler.finish()
    logger.info(
        "Updated %i creation dates and %i modification dates" % (creations, modifieds)
    )
