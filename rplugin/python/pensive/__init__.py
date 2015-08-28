import socket
import threading
import Queue
import os.path
import logging
import sexp
import neovim
import json


class SymbolAtPoint(object):
    name = "SymbolAtPointReq"
    request = None
    response = None

    def create_request(self, path, pos):
        self.request = {
            "typehint": "SymbolAtPointReq",
            "file": path,
            "point": pos
        }
        return json.dumps(self.request)

    def parse_response(self, response):
        self.response = json.loads(response)


class EnsimeCommands(object):
    def connection_info(self):
        return "(swank:connection-info)"

    def init_project(self):
        return "(swank:init-project)"

    def type_check_file(self, path):
        return "(swank:typecheck-file (:file \"{0}\"))".format(path)

    def type_at_point(self, path, line_offset, colnum):
        char_offset = int(line_offset) + int(colnum) - 1
        return '(swank:type-at-point "{0}" {1})'.format(path, char_offset)

    def inspect_type_at_point(self, path, line_offset, colnum):
        char_offset = int(line_offset) + int(colnum) - 1
        return '(swank:inspect-type-at-point "{0}" {1})'.format(
            path, char_offset
        )

    def symbol_at_point(self, path, line_offset, colnum):
        char_offset = int(line_offset) + int(colnum) - 1
        return '(swank:symbol-at-point "{0}" {1})'.format(path, char_offset)

    def doc_at_point(self, path, line_offset, colnum):
        char_offset = int(line_offset) + int(colnum) - 1
        return '(swank:doc-uri-at-point "{0}" {1})'.format(path, char_offset)

    def uses_of_symbol_at_point(self, path, line_offset, colnum):
        char_offset = int(line_offset) + int(colnum) - 1
        return '(swank:uses-of-symbol-at-point "{0}" {1})'.format(
            path, char_offset
        )

    def type_check_all(self):
        return '(swank:typecheck-all)'


class SocketClientThread(threading.Thread):
    def __init__(self, vim, input_queue, output_queue, project_dir):
        super(SocketClientThread, self).__init__()
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(
            logging.FileHandler('/Users/petrov/ensime.log', 'w')
        )
        self.logger.level = logging.DEBUG

        self.vim = vim
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.command_counter = 1
        self.socket = None
        self._connect(project_dir)

        self.handlers = {
            'send': self._send,
            'recv': self._recv,
        }

        self.history = {}

    def run(self):
        import select
        while True:
            try:
                # response = self._recv(None)
                # if response:
                #     continue
                i, o, e = select.select([self.socket], [], [], 0)
                self.logger.debug('input from select %s' % str(i))
                for s in i:
                    if s == self.socket:
                        self._recv(None)

                (cmd, data) = self.input_queue.get(True, 0.1)
                self.logger.debug('cmd: %s' % cmd)
                self.logger.debug('data: %s' % data)
                self.handlers[cmd](data)
            except Queue.Empty:
                self.logger.debug('empty queue exception')
                continue
            except Exception as e:
                self.logger.debug("other exception: %s" % str(e))
                continue

    def _send(self, command):
        wrapped_command = "(:swank-rpc {0} {1})".format(
            command, self.command_counter
        )
        request = "{0}{1}".format(
            "%06x" % len(wrapped_command), wrapped_command
        )
        self.logger.debug(request)
        self.socket.send(request)
        self.command_counter += 1

    def _recv(self, command):
        # get the lenght of incoming message from ensime
        self.logger.debug('receiving...')
        msglen = self.socket.recv(6)
        if msglen:
            msglen = int(msglen, 16)
            self.logger.debug("got msglen")

            buf = ""
            while len(buf) < msglen:
                chunk = self.socket.recv(msglen - len(buf))
                self.logger.debug("chunk: %s" % chunk)
                if chunk:
                    buf += chunk
                else:
                    self.logger.error(
                        "recv returned None while reading from socket"
                    )
                    raise Exception(
                        "recv returned None while reading from socket"
                    )
            response = buf.decode('utf-8').replace('\n', '').replace('\t', '')
            self.output_queue.put(response)
            self.vim.session.threadsafe_call(self._update)
            return response
        return 'invalid message'

    def response_symbol_at_point(self, response):
        key_map = sexp.sexp_to_key_map(sexp.read(response)[1][1])
        pos_map = sexp.sexp_to_key_map(key_map[':decl-pos'])
        filepath = pos_map.get(':file')
        offset = int(pos_map.get(':offset'))

        self.vim.command("sp %s" % filepath)
        self.vim.command("%dgo" % offset)

    def response_type_at_point(self, response):
        key_map = sexp.sexp_to_key_map(sexp.read(response)[1][1])
        output = key_map.get(':name', 'Not available')
        if not key_map[':arrow-type'] and key_map[':type-args']:
            type_maps = [
                sexp.sexp_to_key_map(t) for t in key_map[':type-args']
            ]
            type_names = [str(t[':name']) for t in type_maps]
            output = "%s[%s]" % (
                key_map[':name'], ", ".join(type_names)
            )
        return output

    def _update(self):
        self.logger.debug('calling update')
        result = self.output_queue.get()
        self.logger.debug('output queue result: %s' % str(result))
        output_buffer = [
            b for b in self.vim.buffers if b.name.endswith("pensive")
        ][0]
        output = result

        try:
            self.response_symbol_at_point(result)
        except:
            pass

        try:
            output = self.response_type_at_point(result)

            # output_buffer.append(str(key_map[':decl-pos']))
            # if key_map[':decl-pos']:
            #     pos_map = sexp.sexp_to_key_map(key_map[':decl-pos'])
            #     output_buffer.append(str(pos_map))
            #     filepath = pos_map.get(':file')
            #     output_buffer.append(str(filepath))
            #     offset = self.vim.eval(
            #         'byte2line({0})'.format(
            #             int(pos_map.get(':offset'))
            #         )
            #     )
            #     output_buffer.append(str(offset))
            #     llist = (
            # 'setloclist(0, [{"filename": "%s", "lnum": %d, "text": "%s"}])'
            #     ) % (filepath, offset, 'go here')
            #     output_buffer.append(llist)
            #     self.vim.eval(llist)

        except:
            pass

        output_buffer.append(result)
        output_buffer.append(output)
        # self.vim.current.line = result

    def _connect(self, project_dir):
        line = open(
            os.path.join(project_dir, ".ensime_cache/port"), "r"
        ).read().strip()
        port = int(line)

        self.logger.debug('got the port %d' % port)
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect(('127.0.0.1', port))
        self.logger.debug('connected to server')

    def join(self, timeout=None):
        # self.alive.clear()
        threading.Thread.join(self, timeout)


@neovim.plugin
class EnsimePlugin(object):
    def __init__(self, vim):
        self.vim = vim
        self.project_dir = os.path.abspath(os.path.curdir)
        self.input_queue = Queue.Queue()
        self.output_queue = Queue.Queue()

        self.logger = logging.getLogger(str(self.__class__))
        self.logger.addHandler(
            logging.FileHandler('/Users/petrov/ensime_plugin.log', 'w')
        )
        self.logger.level = logging.DEBUG

    @neovim.command("EnsimeConnect")
    def command_ensime_connect(self):
        has_pensive_buffer = len(
            [b.name for b in self.vim.buffers if b.name.endswith("pensive")]
        ) > 0
        if not has_pensive_buffer:
            self.vim.command("new pensive")
            self.vim.command("resize 10")
            self.vim.command("setlocal buftype=nofile")
            self.vim.command("setlocal bufhidden=hide")
            self.vim.command("setlocal noswapfile")
            self.vim.command("setlocal filetype=scala")
        self.client = SocketClientThread(
            self.vim,
            self.input_queue,
            self.output_queue,
            self.project_dir
        )
        self.client.start()

    @neovim.command("EnsimeTypecheckAll", sync=True)
    def command_typecheck_all(self):
        command = EnsimeCommands().type_check_all()
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeTypecheckFile", sync=True)
    def command_typecheck_file(self):
        filename = self.vim.current.buffer.name
        command = EnsimeCommands().type_check_file(filename)
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeTypeAtPoint", sync=False)
    def command_type_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = EnsimeCommands().type_at_point(
            filename, line_byte_pos, col_number
        )
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeInspectTypeAtPoint", sync=False)
    def command_inspect_type_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = EnsimeCommands().inspect_type_at_point(
            filename, line_byte_pos, col_number
        )
        self.logger.debug('type_at_point: %s' % command)
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeSymbolAtPoint", sync=False)
    def command_symbol_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = EnsimeCommands().symbol_at_point(
            filename, line_byte_pos, col_number
        )
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeSymbolUsesAtPoint", sync=False)
    def command_uses_of_symbol_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = EnsimeCommands().uses_of_symbol_at_point(
            filename, line_byte_pos, col_number
        )
        self.logger.debug('type_at_point: %s' % command)
        self.input_queue.put(('send', command))


def start():
    import neovim
    vim = neovim.attach('socket', path='/tmp/v')

    input_queue = Queue.Queue()
    output_queue = Queue.Queue()
    project_dir = os.path.abspath(os.path.curdir)
    client = SocketClientThread(vim, input_queue, output_queue, project_dir)
    client.start()


if __name__ == "__main__":
    # start()
    import time

    import neovim
    vim = neovim.attach('socket', path='/tmp/v')

    input_queue = Queue.Queue()
    output_queue = Queue.Queue()
    project_dir = os.path.abspath(os.path.curdir)
    client = SocketClientThread(vim, input_queue, output_queue, project_dir)
    client.start()
    while True:
        time.sleep(2)
