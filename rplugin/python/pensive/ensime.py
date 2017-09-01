import os
import json
from operator import attrgetter
from utils import QuickfixEntry

import logging


PENSIVE_COMMAND_LOG = 'pensive-command.log'


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


class VoidResponse(object):
    def __init__(self, payload):
        pass

    def run(self, vim):
        pass


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
            'col': offset,
            'text': line
        }
        return d

    def run(self, vim):
        qflist = [
            self._create_quickfix_entry(pos) for pos in self.positions
        ]

        if qflist:
            vim.eval("setloclist(0, %s)" % str(qflist))
            vim.command("lopen")

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
        # self.type_id = payload['typeId']
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
            "%s%s" % (t.full_name, t._get_type_args()) for t in self.type_args
        ]
        return "[%s]" % ",".join(type_args)

    def run(self, vim):
        result = self.full_name
        # self.output_buffer(vim).append(self.name + self._get_type_args())
        vim.command("echom '%s'" % result)

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'BasicTypeInfo'


class ArrowTypeInfo(TypeInfo):
    def __init__(self, payload):
        self.name = payload['name']
        self.full_name = payload['resultType']['fullName']
        # self.type_id = payload['typeId']
        self.result_type = TypeInfo.fromJson(payload['resultType'])
        self.param_sections = None
        self.decl_as = None
        self.type_args = None
        self.members = None
        self.pos = None
        self.outer_type_id = None

    def run(self, vim):
        # self.output_buffer(vim).append(self.name)
        vim.command("echom '%s'" % self.name)

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'ArrowTypeInfo'


class SourcePosition(ResponseType):
    def goto(self, vim):
        pass


class EmptySourcePosition(SourcePosition):
    @classmethod
    def handles(cls, payload):
        return False


class OffsetSourcePosition(SourcePosition):
    def __init__(self, payload):
        self.file = payload['file']
        self.offset = payload['offset']

    def goto(self, vim):
        vim.command("sp %s" % self.file)
        vim.command("%dgo" % self.offset)

    @classmethod
    def handles(cls, payload):
        return 'offset' in payload


class LineSourcePosition(SourcePosition):
    def __init__(self, payload):
        self.file = payload['file']
        self.line = payload['line']

    def goto(self, vim):
        vim.command("sp %s" % self.file)
        vim.command("%dG" % self.line)

    @classmethod
    def handles(cls, payload):
        return 'line' in payload


class SymbolInfo(object):
    def __init__(self, payload):
        self.plugin_dir = os.path.dirname(os.path.realpath(__file__))
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(
            logging.FileHandler(
                os.path.join(self.plugin_dir, PENSIVE_COMMAND_LOG), 'w')
        )
        self.logger.level = logging.DEBUG
        self.name = payload.get('name')
        self.logger.debug("name: %s" % self.name)
        self.local_name = payload.get('localName')
        self.logger.debug("local_name: %s" % self.local_name)
        self.decl_pos = SourcePosition.fromJson(payload.get('declPos'))
        self.logger.debug("decl_pos: %s" % self.decl_pos)
        self.type = TypeInfo.fromJson(payload.get('type'))
        self.logger.debug("type: %s" % self.type)
        self.is_callable = payload.get('isCallable')
        self.logger.debug("is_callable: %s" % self.is_callable)
        self.owner_type_id = payload.get('ownerTypeId')
        self.logger.debug("owner_type_id: %s" % self.owner_type_id)

    def run(self, vim):
        # if the symbol declaration is the same as the type position
        # just go to the declaration position
        df = getattr(self.decl_pos, 'file', False)
        tf = getattr(self.type, 'file', False)

        if df and tf and df == tf:
            self.decl_pos.goto(vim)
        else:
            if self.type and self.type.pos:
                self.type.pos.goto(vim)
            elif self.decl_pos:
                self.decl_pos.goto(vim)


def add_class_name(d, cls):
    d['__name__'] = cls.__class__.__name__
    return d


class UnloadAll(object):
    typehint = "UnloadAllReq"
    _request = None
    _response = None

    def request(self):
        self._request = {"typehint": self.typehint}
        return add_class_name(self._request, self)

    def response(self, content):
        self._response = json.loads(content)
        return self._response


class ConnectionInfo(object):
    typehint = "ConnectionInfoReq"
    _request = None
    _response = None

    def request(self):
        self._request = {"typehint": self.typehint}
        return add_class_name(self._request, self)

    def response(self):
        pass


class TypecheckAll(object):
    typehint = "TypecheckAllReq"
    _request = None
    _response = None

    def request(self):
        self._request = {"typehint": self.typehint}
        return add_class_name(self._request, self)

    def response(self, payload):
        self._response = VoidResponse(payload)
        return self._response


class TypecheckFile(object):
    typehint = "TypecheckFilesReq"
    _request = None
    _response = None

    def request(self, path):
        self._request = {
            "typehint": self.typehint,
            "files": [path]
        }
        return add_class_name(self._request, self)

    def response(self, payload):
        # self._response = NewScalaNotesEvent(payload)
        self._response = Notification.fromJson(payload)
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


class TypeOfSelection(object):
    typehint = "TypeAtPointReq"
    _request = None
    _response = None

    def request(self, path, start, end):
        self._request = {
            "typehint": self.typehint,
            "file": path,
            "range": {"from": start, "to": end}
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


# class CompletionsReq(object):
#     typehint = "CompletionsReq"
#     _request = None
#     _response = None

#     def request(self, path, pos):
#         self._request = {
#             "typehint": self.typehint,
#             "file": path,
#             "point": pos
#         }
#         return add_class_name(self._request, self)

#     def response(self, payload):
#         self._response = CompletionInfos(payload)
#         return self._response

#     def response(self, payload):
#         return self._response


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


class Notification(ResponseType):
    def __init__(self, parsed_command):
        self.parsed_command = parsed_command


class NewScalaNotesEvent(Notification):
    def __init__(self, parsed_command):
        super(NewScalaNotesEvent, self).__init__(parsed_command)
        self.notes = self.parsed_command['notes']

    def _create_quickfix_entry(self, pos):
        severities = {
            'NoteError': 'E',
            'NoteWarning': 'W'
        }

        d = {
            'filename': str(pos['file']),
            'lnum': pos['line'],
            'col': pos['col'],
            'text': str(pos['msg']),
            'type': severities.get(pos['severity']['typehint'], '')
        }

        return d

    def run(self, vim):
        current_qf_list = vim.eval('getqflist()')
        deref_qf_list = []

        for d in current_qf_list:
            d['file'] = vim.eval('bufname(%s)' % d['bufnr'])
            deref_qf_list.append(d)

        qflist = [
            QuickfixEntry.fromVim(i) for i in deref_qf_list
        ] + [
            QuickfixEntry.fromScalaNote(i) for i in self.notes
        ]

        qflist = sorted(
            list(set(qflist)),
            key=attrgetter('filename', 'line_number', 'severity')
        )

        if qflist:
            vim.eval("setqflist(%s)" % str([i.to_dict() for i in qflist]))

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'NewScalaNotesEvent'


class ClearScalaNotes(Notification):
    def run(self, vim):
        vim.command("echom 'Cleared Scala notes'")
        vim.eval('setqflist([])')

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'ClearAllScalaNotesEvent'


class IndexerReady(Notification):
    def run(self, vim):
        vim.command("echom 'Indexer Ready'")

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'IndexerReadyEvent'


class AnalyzerReady(Notification):
    def run(self, vim):
        vim.command("echom 'Analyzer Ready'")

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'AnalyzerReadyEvent'


class FullTypeCheckComplete(Notification):
    def run(self, vim):
        vim.command("echom 'Full Typecheck Complete'")

    @classmethod
    def handles(cls, payload):
        return payload.get('typehint', '') == 'FullTypeCheckCompleteEvent'
