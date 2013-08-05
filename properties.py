from types import FunctionType
from inspect import getargspec
from decimal import Decimal
from datetime import datetime
from util import IN, OUT

__all__ = ['Boolean', 'String', 'Integer', 'Float', 'Numeric', 'DateTime',
           'Array', 'RelOut', 'RelIn', 'RelOutOne', 'RelInOne']

class FieldDescriptor(object):

    def __init__(self, name=None):
        self._name = None
        self.name = name

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, name):
        if self._name is None:
            self._name = name

class Property(FieldDescriptor):

    __value_type__ = None

    def __init__(self, name=None, default=None):
        super(Property, self).__init__(name)
        self._default = default

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        else:
            value = instance.properties.get(self.name)
            return self.normalize(value if value is not None else self.get_default(instance))
    
    def __set__(self, instance, value):
        instance.properties[self.name] = self.normalize(value)
    
    def __delete__(self, instance):
        del instance.properties[self.name]

    def get_default(self, instance):
        if hasattr(self._default, '__call__'):
            if isinstance(self._default, FunctionType) and len(getargspec(self._default).args) == 1:
                return self._default(instance)
            else:
                return self._default()
        else:
            return self._default

    def normalize(self, value):
        if value is not None and self.__value_type__ is not None:
            if not isinstance(value, self.__value_type__):
                value = self.__value_type__(value)
        return value

class Boolean(Property):

    __value_type__ = bool

class String(Property):

    __value_type__ = unicode

class Integer(Property):

    __value_type__ = int

class Float(Property):

    __value_type__ = float

class Numeric(Property):

    __value_type__ = Decimal

    def __init__(self, scale=None, name=None, default=None):
        super(Numeric, self).__init__(name=name, default=default)
        self.scale = scale
    
    def __set__(self, instance, value):
        if value is not None:
            value = str(value)
        instance.properties[self.name] = value

    def normalize(self, value):
        value = super(Numeric, self).normalize(value)
        if self.scale is not None and isinstance(value, Decimal):
            value = value.quantize(Decimal('1.' + '0' * self.scale))
        return value

class DateTime(Property):

    __value_type__ = datetime

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        else:
            value = instance.properties.get(self.name)
            if value is not None and not isinstance(value, datetime):
                value = self.parse(value)
            return value if value is not None else self.get_default(instance)
    
    def __set__(self, instance, value):
        if isinstance(value, datetime):
            value = value.strftime("%Y-%m-%d %H:%M:%S")
        instance.properties[self.name] = value

    @classmethod
    def parse(cls, value):
        if isinstance(value, basestring):
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M")
            except ValueError:
                pass
            try:
                return datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                pass
            try:
                return datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                pass
            try:
                return datetime.strptime(value, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                pass
        elif isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)
        return None

class Array(Property):

    __value_type__ = list

    def __init__(self, type=None, name=None):
        super(Array, self).__init__(name=name)
        self._content_type = type

    def __get__(self, instance, owner=None):
        value = super(Array, self).__get__(instance, owner)
        if instance is not None and not isinstance(value, TypedList):
            value = TypedList(value, type=self._content_type)
            super(Array, self).__set__(instance, value)
        return value

    def __set__(self, instance, value):
        if not isinstance(value, TypedList):
            value = TypedList(value, type=self._content_type)
        super(Array, self).__set__(instance, value)

class TypedList(list):
    
    # TODO: implement type checking, casting and enforcing

    def __init__(self, list=None, type=None):
        super(TypedList, self).__init__(list or [])
        self._content_type = type

class RelDescriptor(FieldDescriptor):

    def __init__(self, direction, type, name=None, target=None, multiple=False):
        super(RelDescriptor, self).__init__(name=name)
        self.direction = direction
        self.type = type
        self.target = target
        self.single = False
        self.multiple = multiple if target is None else False

    def get_relview(self, instance):
        try:
            return instance._relfilters[self.name]
        except KeyError:
            from relmap import RelView
            instance._relfilters[self.name] = RelView(instance, self.direction, self.type,
                                                      target=self.target,
                                                      single=self.single,
                                                      multiple=self.multiple)
            return instance._relfilters[self.name]

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        else:
            return self.get_relview(instance)

class RelOut(RelDescriptor):

    def __init__(self, *args, **kwargs):
        super(RelOut, self).__init__(OUT, *args, **kwargs)

class RelIn(RelDescriptor):

    def __init__(self, *args, **kwargs):
        super(RelIn, self).__init__(IN, *args, **kwargs)

class RelDescriptorOne(RelDescriptor):

    def __init__(self, *args, **kwargs):
        super(RelDescriptorOne, self).__init__(*args, **kwargs)
        self.single = True
        self.multiple = False

    def __get__(self, instance, owner=None):
        if instance is None:
            return self
        else:
            relview = self.get_relview(instance)
            try:
                return relview[0]
            except IndexError:
                return None

    def __set__(self, instance, value):
        relview = self.get_relview(instance)
        current = list(relview)

        if value is None:
            for item in current:
                relview.remove(item)
        elif len(current) == 0:
            relview.append(value)
        elif len(current) == 1 and current[0] is not value:
            relview.remove(current[0])
            relview.append(value)
        elif len(current) > 1:
            removed = []
            for item in current:
                if item is not value:
                    relview.remove(item)
                    removed.append(item)
            if len(removed) == len(current):
                relview.append(value)

class RelOutOne(RelDescriptorOne):

    def __init__(self, *args, **kwargs):
        super(RelOutOne, self).__init__(OUT, *args, **kwargs)

class RelInOne(RelDescriptorOne):

    def __init__(self, *args, **kwargs):
        super(RelInOne, self).__init__(IN, *args, **kwargs)
