import threading
from itertools import chain
from py2neo import neo4j

class Session(object):

    def __init__(self, metadata=None):
        self._threadlocal = threading.local()
        self._metadata = metadata

    def clear(self):
        self.nodes.clear()
        self.phantomnodes.clear()
        self.relmap.clear()

    @property
    def nodes(self):
        try:
            return self._threadlocal.nodes
        except AttributeError:
            self._threadlocal.nodes = {}
            return self._threadlocal.nodes

    @property
    def phantomnodes(self):
        try:
            return self._threadlocal.phantomnodes
        except AttributeError:
            self._threadlocal.phantomnodes = set()
            return self._threadlocal.phantomnodes

    @property
    def relmap(self):
        try:
            return self._threadlocal.relmap
        except AttributeError:
            from relationship import RelationshipMapper
            self._threadlocal.relmap = RelationshipMapper()
            return self._threadlocal.relmap

    @property
    def count(self):
        return len(self.nodes) + len(self.phantomnodes) + len(self.relmap)

    @property
    def new(self):
        return len(self.phantomnodes) + len(self.relmap._phantoms)

    @property
    def dirty(self):
        return sum((1 for x in chain(self.nodes.itervalues(), self.relmap.iterpersisted()) if x.is_dirty()))

    def is_dirty(self):
        return self.new + self.dirty > 0

    def add_entity(self, entity):
        from relationship import Relationship
        if isinstance(entity, Relationship):
            self.relmap.add(entity)
        else:
            if entity.is_phantom():
                self.phantomnodes.add(entity)
            else:
                self.phantomnodes.discard(entity)
                self.nodes[entity.id] = entity

    def get_entity(self, value):
        if isinstance(value, neo4j.Node):
            return self.nodes.get(value.id)
        elif isinstance(value, (neo4j.Relationship, tuple)):
            return self.relmap.get(value)
        else:
            return None

    def expunge(self, entity):
        from relationship import Relationship
        if isinstance(entity, Relationship):
            self.relmap.remove(entity)
        else:
            self.phantomnodes.discard(entity)
            self.nodes.pop(entity.id, None)

    def rollback(self):
        for entity in chain(self.nodes.itervalues(), self.relmap.itervalues()):
            entity.rollback()
        self.clear()

    def commit(self):
        # TODO Batch-ify
        while self.phantomnodes:
            self.phantomnodes.pop().save()
        for entity in chain(self.nodes.itervalues(), self.relmap.itervalues()):
            entity.save()
