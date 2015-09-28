severities = {
    'NoteError': 'E',
    'NoteWarning': 'W'
}


class QuickfixEntry(object):
    def __init__(self):
        self.filename = None
        self.line_number = None
        self.column = None
        self.description = None
        self.severity = None

    def __repr__(self):
        return '[QuickfixEntry: %s]' % str(self.to_dict())

    def __eq__(self, other):
        if not isinstance(other, QuickfixEntry):
            return False

        return (
            self.filename == other.filename and
            self.line_number == other.line_number and
            self.column == other.column and
            self.description == other.description and
            self.severity == other.severity
        )

    def __ne__(self, other):
        return not self.__eq__(other)

    def __hash__(self):
        return (
            self.filename.__hash__() +
            self.line_number.__hash__() +
            self.column.__hash__() +
            self.description.__hash__() +
            self.severity.__hash__()
        )

    def to_dict(self):
        result = {}
        if self.filename:
            result['filename'] = self.filename
        if self.line_number is not None:
            result['lnum'] = self.line_number
        if self.column is not None:
            result['col'] = self.column
        if self.text is not None:
            result['text'] = self.text
        if self.severity is not None:
            result['type'] = self.severity

        return result

    @classmethod
    def fromScalaNote(cls, payload):
        # def get_severity(payload):
        #     severity = payload.get('severity', None)
        #     if not severity:
        #         return
        #     severity_type = severity.get('typehint', None)
        #     return severity_type

        entry = QuickfixEntry()
        entry.filename = str(payload['file'])
        entry.line_number = payload['line']
        entry.column = payload['col']
        entry.text = str(payload['msg'])
        entry.severity = severities.get(payload['severity']['typehint'], '')
        return entry

    @classmethod
    def fromVim(cls, payload):
        entry = QuickfixEntry()
        entry.filename = str(payload['file'])
        entry.line_number = payload['lnum']
        entry.column = payload['col']
        entry.text = str(payload['text'])
        entry.severity = payload['type']
        return entry
