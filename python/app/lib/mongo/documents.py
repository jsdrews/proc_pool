import sys
import inspect
import pymongo
from bson.objectid import ObjectId
from bson.errors import InvalidId, InvalidDocument


def validate_object_id(object_id):
    """
    Helper method to keep the object id validation in one place
    :param object_id:
    :return:
    """
    try:
        oid = None
        if isinstance(object_id, str):
            oid = ObjectId(object_id)
        elif isinstance(object_id, ObjectId):
            oid = object_id
        assert oid
    except (InvalidId, AssertionError):
        raise UserFault('object id must be either a valid object id hash')

    return oid


class Fault(Exception):
    pass


class UserFault(Fault):
    pass


class ApplicationFault(Fault):
    pass


class Children(object):

    __slots__ = (
        'type',
        'children',
    )

    def __init__(self, child_type, children=None):
        self.type = child_type
        if children:
            assert isinstance(children, list)
        self.children = children or []

    def __setitem__(self, key, value):
        try:
            assert isinstance(value, getattr(sys.modules[__name__], self.type))
            self.children[key] = value
        except IndexError:
            self.children.append(value)
        except AssertionError:
            raise UserFault('Child must be type "{}" -- received: "{}"'.format(self.type, type(value).__name__))

    def __getitem__(self, item):
        try:
            return self.children[item]
        except IndexError:
            return None

    def __len__(self):
        return len(self.children)

    def append(self, child):
        try:
            assert isinstance(child, getattr(sys.modules[__name__], self.type))
            self.children.append(child)
        except AssertionError:
            raise UserFault('Child must be type "{}" -- received: "{}"'.format(self.type, type(child).__name__))

    def extend(self, child_list):
        try:
            assert isinstance(child_list, list)
            for child in child_list:
                self.append(child)
        except AssertionError:
            raise UserFault('Children.extend requires a list')

    def get(self, key, value):
        for child in self.children:
            if getattr(child, key) == value:
                return child
        return None

    @property
    def list(self):
        return self.children


class Client(object):
    
    URL = None
    CLIENT = None
    DB_NAME = None
    
    @staticmethod
    def get_client():
        return Client.CLIENT
    
    @staticmethod
    def set(url, db_name):
        Client.URL = url
        Client.DB_NAME = db_name
        Client.CLIENT = getattr(pymongo.MongoClient(Client.URL), Client.DB_NAME)

    @staticmethod
    def override_client(client):
        Client.CLIENT = client

    @staticmethod
    def next(collection_name, query, sort_by):
        assert Client.CLIENT, "Before talking to the instance of Mongodb, set the Client with Client.set(url, db_name)"
        assert Document.__name__.lower() != collection_name,\
            "This opperation cannot be performed on the Document base class"

        try:
            return getattr(Client.CLIENT, collection_name).find(query).sort([(sort_by, -1)]).limit(1).next()
        except StopIteration:
            return {}

    @staticmethod
    def find(collection_name, query):
        return [x for x in getattr(Client.CLIENT, collection_name).find(Client.__sanitize_query(query))]

    @staticmethod
    def find_one(collection_name, query):
        assert Client.CLIENT, "Before talking to the instance of Mongodb, set the Client with Client.set(url, db_name)"
        assert Document.__name__.lower() != collection_name, \
            "This opperation cannot be performed on the Document base class"

        return getattr(Client.CLIENT, collection_name).find_one(Client.__sanitize_query(query))

    @staticmethod
    def update_one(collection_name, filter_data, action):
        assert Client.CLIENT, "Before talking to the instance of Mongodb, set the Client with Client.set(url, db_name)"
        assert Document.__name__.lower() != collection_name, \
            "This opperation cannot be performed on the Document base class"

        try:
            getattr(Client.CLIENT, collection_name).update_one(filter_data, action)
        except InvalidDocument as e:
            raise ApplicationFault('The following issue occurred while trying to insert this document {}'.format(e))

    @staticmethod
    def insert(collection_name, data):
        assert Client.CLIENT, "Before talking to the instance of Mongodb, set the Client with Client.set(url, db_name)"
        assert Document.__name__.lower() != collection_name, \
            "This opperation cannot be performed on the Document base class"

        try:
            return getattr(Client.CLIENT, collection_name).insert(data)
        except InvalidDocument as e:
            raise ApplicationFault('The following issue occurred while trying to insert this document {}'.format(e))

    @staticmethod
    def remove(collection_name, data):
        assert Client.CLIENT, "Before talking to the instance of Mongodb, set the Client with Client.set(url, db_name)"
        assert Document.__name__.lower() != collection_name, \
            "This opperation cannot be performed on the Document base class"
        return getattr(Client.CLIENT, collection_name).remove(data)

    @staticmethod
    def __sanitize_query(query_data):
        assert Client.CLIENT, "Before talking to the instance of Mongodb, set the Client with Client.set(url, db_name)"

        def __object_convert(oid):
            try:
                return ObjectId(oid)
            except (InvalidId, TypeError) as e:
                return None

        tmp = {}
        for k, v in query_data.items():
            if k == '_id':
                if isinstance(v, dict):
                    tmpd = {}
                    for filt, vals in v.items():
                        tmpl2 = []
                        for i in vals:
                            i = str(i)
                            o = __object_convert(i)
                            if o:
                                tmpl2.append(o)
                        if tmpl2:
                            tmpd[filt] = tmpl2
                    if tmpd:
                        tmp[k] = tmpd
                else:
                    o = __object_convert(v)
                    tmp[k] = o
            else:
                tmp[k] = v

        return tmp


class Document(object):

    SCHEMA = {
        'children': (),
        'parent': (),
    }

    __slots__ = (
        'parent',
        '_id',
        '__type',
        '__collection',
        '__children_key',
        '__children_type',
        '__parent_key',
        '__parent_type',
    )

    def __init__(self, *args, **kwargs):

        self._id = ''
        self.__type = self.__class__.__name__

        self.__children_key = None
        self.__children_type = None

        if self.__class__.SCHEMA.get('children'):
            self.__children_key = self.__class__.SCHEMA.get('children')[0]
            self.__children_type = self.__class__.SCHEMA.get('children')[1]
            setattr(self, self.__children_key, Children(self.__children_type))

        self.__parent_key = None
        self.__parent_type = None

        if self.__class__.SCHEMA.get('parent'):
            self.__parent_key = self.__class__.SCHEMA.get('parent')[0]
            self.__parent_type = self.__class__.SCHEMA.get('parent')[1]
            setattr(self, self.__parent_key, None)

        tmp = dict(*args, **kwargs)
        for k, v in tmp.items():
            if k == self.__children_key:
                class_ = globals()[self.__children_type]
                att = getattr(self, k)
                for child in v:
                    att.append(class_(child))
                continue
            setattr(self, k, v)

    def __setattr__(self, key, value):
        previous_frame = inspect.currentframe().f_back.f_code.co_name
        try:
            if previous_frame not in ('__init__', 'insert', 'remove'):
                assert not key.startswith('_')
            super(Document, self).__setattr__(key, value)
        except (AttributeError, AssertionError) as e:
            raise UserFault('The {} document only allows for the following keys:'
                            '\n{}'.format(self.__type, '\n'.join(self.__slots__)))

    def __getattr__(self, item):
        try:
            return super(Document, self).__getattribute__(item)
        except AttributeError:
            return None

    def __repr__(self):
        return str(self.id or self.__class__.__name__)

    def __str__(self):
        return str(self.id or self.__class__.__name__)

    def __bool__(self):
        return bool(self.id)

    @classmethod
    def query(cls, query):
        return [cls(x) for x in Client.find(cls.__name__.lower(), query)]

    @classmethod
    def from_id(cls, object_id):
        collection_name = cls.__name__.lower()

        if collection_name == 'document':
            raise UserFault('Cannot retrieve a document from the parent base class: Document -- use a subclass')

        oid = validate_object_id(object_id)

        document = Client.find_one(collection_name, {'_id': oid})

        if not document:
            return cls()

        return cls(document)

    @property
    def collection(self):
        return self.__class__.__name__.lower()

    @property
    def id(self):
        return self._id

    @property
    def name(self):
        return str(self._id)

    @property
    def type(self):
        return self.__type

    @property
    def dict(self):
        tmp = {}
        for key in self.__slots__:
            attribute = getattr(self, key)
            if key == self.__children_key:
                try:
                    tmp.update({key: [x.dict for x in attribute.list]})
                    continue
                except:
                    pass
            tmp.update({key: attribute})
        return tmp

    @property
    def full(self):
        """
        Return a dict without the children key
        :return:
        """
        tmp = {}
        for key in self.__slots__:
            attribute = getattr(self, key)
            if key == self.__children_key:
                continue
            tmp.update({key: attribute})
        tmp['id'] = str(self.id)
        return tmp

    def pp(self):
        from pprint import pprint
        pprint(self.full)

    def insert(self, status=None):

        if self._id:
            raise UserFault('You are trying to insert a document that has already been inserted')

        try:
            self.status = status or 'created'
        except UserFault:
            pass

        self._id = Client.insert(self.collection, self.dict)
        return True

    def commit(self, status=None):

        if not self._id:
            return self.insert(status=status)

        if status:
            try:
                self.status = status
            except (UserFault, AttributeError):
                pass

        Client.update_one(self.collection, {'_id': self._id}, {'$set': self.dict})
        return True

    def remove(self):

        if not self._id:
            raise UserFault('You cannot remove a document that hasn\'t been created yet or is not inserted')

        ret = Client.remove(self.collection, {'_id': self._id})
        if bool(ret.get('n')):
            self._id = ''

        return bool(ret.get('n'))
