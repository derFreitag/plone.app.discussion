# -*- coding: utf-8 -*-
from Products.CMFCore.utils import getToolByName


def index_object(obj, event):
    """Index the object when it is added to the conversation.
    """
    obj.indexObject()


def unindex_object(obj, event):
    """Unindex the object when it is removed from the conversation.
    """
    obj.unindexObject()


def modified_object(obj, event):
    """Reindex the object when it is modified.
    """
    obj.reindexObject()
