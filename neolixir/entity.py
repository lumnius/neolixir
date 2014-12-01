import overrides
import py2neo
from py2neo import neo4j
from utils import classproperty
from metadata import metadata as m
from properties import Property, FieldDescriptor
from observable import Observable, ObservableMeta

__all__ = ['Entity']

class EntityMeta(ObservableMeta):

    def __init__(cls, name, bases, dict_):
        super(EntityMeta, cls).__init__(name, bases, dict_)

        # inherited descriptors
        cls._descriptors = cls._descriptors.copy() if hasattr(cls, '_descriptors') else {}
        for base in bases:
            if hasattr(base, '_descriptors'):
                for k, v in base._descriptors.iteritems():
                    if k not in cls._descriptors:
                        cls._descriptors[k] = v

        # class-defined descriptors
        for k, v in dict_.iteritems():
            if isinstance(v, FieldDescriptor):
                cls._descriptors[k] = v
                v.name = k
        
        m.add(cls)

class Entity(Observable):

    """Base class for all Neolixir entities (Nodes and Relationships).
    
    Defines basic shared functionality and handles proper subclassing and 
    instance initialization, instance registration and descriptor setup.

    Should not be used directly, always use :class:`node.Node` or 
    :class:`relationship.Relationship` instead.

    :param value: A :class:`py2neo.neo4j.Node` or :class:`py2neo.neo4j.Relationship` instance, or None.
    :param \*\*properties: Keyword arguments will be used to initialize the entity's properties.
    :returns: An :class:`Entity` or a subclass thereof.
    
    """
    
    __metaclass__ = EntityMeta

    _initialized = False
    _deleted = False

    def __new__(cls, value=None, **properties):
        if isinstance(value, cls):
            return value
        instance = m.session.get(value)
        if instance is not None:
            return instance
        elif isinstance(value, (neo4j.Node, neo4j.Relationship)):
            loaded_properties = m.session.propmap.get_properties(value)
            valcls = m.classes.get(loaded_properties.get('__class__'))
            if not valcls or not issubclass(valcls, cls):
                raise TypeError("entity is not an instance of " + cls.__name__)
            instance = super(Entity, cls).__new__(valcls)
            instance._entity = value
            if valcls is not cls:
                instance.__init__(value, **properties)
            return instance
        else:
            instance = super(Entity, cls).__new__(cls)
            instance._entity = None
            return instance

    def __init__(self, value=None, **properties):
        if not self._initialized:
            self._initialized = True
            for k, v in properties.iteritems():
                if k in self._descriptors:
                    setattr(self, k, v)
                else:
                    self.properties[k] = v
            m.session.add(self)

    def __copy__(self):
        # TODO: support copying?
        return self

    def __deepcopy__(self, memo):
        # TODO: support deepcopying?
        return self

    def _get_repr_data(self):
        return ["Id = {0}".format(self.id),
                "Descriptors = {0}".format(sorted(self.descriptors.keys())),
                "Properties = {0}".format(self.properties)]

    def __repr__(self):
        return "<{0} (0x{1:x}): \n{2}\n>".format(self.__class__.__name__, id(self),
                                                 "\n".join(self._get_repr_data()))

    @property
    def _entity(self):
        return self.__entity

    @_entity.setter
    def _entity(self, value):
        self.__entity = value
        if value is not None:
            value.properties

    @property
    def cls(self):
        return self.__class__

    @property
    def id(self):
        return self._entity.id if self._entity else None

    @property
    def descriptors(self):
        return self._descriptors

    @property
    def properties(self):
        try:
            return self._properties
        except AttributeError:
            self._properties = m.session.propmap.get_properties(self)
            self._properties.owner = self
            return self._properties

    def get_properties(self):
        data = {}
        for k, v in self._descriptors.iteritems():
            if isinstance(v, Property):
                data[k] = getattr(self, k)
        for k, v in self.properties.iteritems():
            data.setdefault(k, v)
        return data

    def set_properties(self, data):
        for k, v in data.iteritems():
            if k in self._descriptors:
                setattr(self, k, v)
            else:
                self.properties[k] = v

    def get_abstract(self):
        self.properties.sanitize()
        return self.properties

    def set_entity(self, entity):
        if self._entity is None:
            self._entity = entity
            try:
                del self._properties
            except AttributeError:
                pass
            if getattr(self, '_session', None):
                self._session.add(self)
            return True
        else:
            return False

    def is_phantom(self):
        return self._entity is None

    def is_deleted(self):
        return self._deleted

    def is_dirty(self):
        if self.is_deleted():
            return True
        elif not hasattr(self, '_properties'):
            return False
        else:
            return self.properties.is_dirty()

    def expunge(self):
        if getattr(self, '_session', None):
            self._session.expunge(self)
            self._session = None

    def rollback(self):
        self._deleted = False
        try:
            del self._properties
        except AttributeError:
            pass

    def delete(self):
        self._deleted = True
        if self.is_phantom():
            self.expunge()

    def save(self, batch=None):
        raise NotImplementedError("cannot save through generic Entity class")
