import json


class ResponseType(object):
    @classmethod
    def fromJson(cls, payload):
        for subclass in cls._handlers():
            if subclass.handles(payload):
                return subclass(payload)

    @classmethod
    def _handlers(cls):
        for c in cls.__subclasses__():
            yield c


class ERangePosition(object):
    def __init__(self, payload):
        self.file = payload['file']
        self.offset = payload['offset']


class ERangePositions(object):
    def __init__(self, payload):
        self.positions = [
            ERangePosition(pos) for pos in payload['positions']
        ]

    def _create_quickfix_entry(self, pos):
        import os
        offset = pos.offset
        fh = open(pos.file, 'r')
        for line_num, line in enumerate(fh, 1):
            line_len = len(line)
            if (offset - line_len) < 0:
                break
            offset = offset - line_len
        fh.close()
        d = {
            'filename': str(
                pos.file.replace(
                    os.path.abspath(os.path.curdir) + '/', ''
                )
            ),
            'lnum': line_num,
            'col': offset
        }
        return d

    def output_buffer(self, vim):
        return [
            b for b in vim.buffers if b.name.endswith("pensive")
        ][0]

    def run(self, vim):
        qflist = [
            self._create_quickfix_entry(pos) for pos in self.positions
        ]
        self.output_buffer(vim).append(str(qflist))
        vim.eval("setqflist(%s)" % str(qflist))

    @classmethod
    def fromJson(cls, payload):
        return cls(payload)


class TypeInfo(ResponseType):
    def output_buffer(self, vim):
        return [
            b for b in vim.buffers if b.name.endswith("pensive")
        ][0]

    def run(self, vim):
        pass


class BasicTypeInfo(TypeInfo):
    def __init__(self, payload):
        self.name = payload['name']
        self.type_id = payload['typeId']
        self.decl_as = None
        self.full_name = payload['fullName']
        self.type_args = [
            TypeInfo.fromJson(t) for t in payload['typeArgs']
        ]
        self.members = None
        pos = payload.get('pos')
        self.pos = SourcePosition.fromJson(pos) if 'pos' in payload else None
        self.outer_type_id = None

    def _get_type_args(self):
        if not self.type_args:
            return ''
        type_args = [
            "%s%s" % (t.name, t._get_type_args()) for t in self.type_args
        ]
        return "[%s]" % ",".join(type_args)

    def run(self, vim):
        self.output_buffer(vim).append(self.name + self._get_type_args())

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'BasicTypeInfo'


class ArrowTypeInfo(TypeInfo):
    def __init__(self, payload):
        self.name = payload['name']
        self.full_name = payload['resultType']['fullName']
        self.type_id = payload['typeId']
        self.result_type = TypeInfo.fromJson(payload['resultType'])
        self.param_sections = None
        self.decl_as = None
        self.type_args = None
        self.members = None
        self.pos = None
        self.outer_type_id = None

    def run(self, vim):
        self.output_buffer(vim).append(self.name)

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'ArrowTypeInfo'


class SourcePosition(ResponseType):
    pass


class EmptySourcePosition(SourcePosition):
    @classmethod
    def handles(cls, payload):
        return False


class OffsetSourcePosition(SourcePosition):
    def __init__(self, payload):
        self.file = payload['file']
        self.offset = payload['offset']

    @classmethod
    def handles(cls, payload):
        return 'offset' in payload


class LineSourcePosition(SourcePosition):
    def __init__(self, payload):
        self.file = payload['file']
        self.line = payload['line']

    @classmethod
    def handles(cls, payload):
        return 'line' in payload


class SymbolInfo(object):
    def __init__(self, payload):
        self.name = payload['name']
        self.local_name = payload['localName']
        self.decl_pos = SourcePosition.fromJson(payload.get('declPos'))
        self.type = TypeInfo.fromJson(payload['type'])
        self.is_callable = payload['isCallable']
        self.owner_type_id = payload['ownerTypeId']

    def run(self, vim):
        vim.command("sp %s" % self.decl_pos.file)
        if isinstance(self.decl_pos, OffsetSourcePosition):
            vim.command("%dgo" % self.decl_pos.offset)
        if isinstance(self.decl_pos, LineSourcePosition):
            vim.command("%dG" % self.decl_pos.line)


def add_class_name(d, cls):
    d['__name__'] = cls.__class__.__name__
    return d


class TypecheckAll(object):
    typehint = "TypecheckAllReq"
    _request = None
    _response = None

    def request(self):
        self._request = {"typehint": self.typehint}
        return add_class_name(self._request, self)

    def response(self, content):
        self._response = json.loads(content)
        return self._response


class TypecheckFile(object):
    typehint = "TypecheckFileReq"
    _request = None
    _response = None

    def request(self, path):
        self._request = {
            "typehint": self.typehint,
            "fileInfo": {"file": path}
        }
        return add_class_name(self._request, self)

    def response(self, content):
        self._response = json.loads(content)
        return self._response


class TypeAtPoint(object):
    typehint = "TypeAtPointReq"
    _request = None
    _response = None

    def request(self, path, pos):
        self._request = {
            "typehint": self.typehint,
            "file": path,
            "range": {"from": pos, "to": pos}
        }
        return add_class_name(self._request, self)

    def response(self, payload):
        self._response = TypeInfo.fromJson(payload)
        return self._response


class SymbolAtPoint(object):
    typehint = "SymbolAtPointReq"
    _request = None
    _response = None

    def request(self, path, pos):
        self._request = {
            "typehint": self.typehint,
            "file": path,
            "point": pos
        }
        return add_class_name(self._request, self)

    def response(self, payload):
        self._response = SymbolInfo(payload)
        return self._response


class UsesOfSymbolAtPoint(object):
    typehint = "UsesOfSymbolAtPointReq"
    _request = None
    _response = None

    def request(self, path, pos):
        self._request = {
            "typehint": self.typehint,
            "file": path,
            "point": pos
        }
        return add_class_name(self._request, self)

    def response(self, payload):
        self._response = ERangePositions(payload)
        return self._response


class ImplicitInfo(object):
    typehint = "ImplicitInfoReq"
    _request = None
    _response = None

    def request(self, path, start, end):
        self._request = {
            'typehint': self.typehint,
            'file': path,
            'range': {'from': start, 'to': end}
        }
        return add_class_name(self._request, self)

    def response(self, payload):
        self._response = payload
        return self._response
