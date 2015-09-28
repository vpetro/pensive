import socket
import threading
import Queue
import os.path
import logging
import neovim
import json
import ensime


PENSIVE_SOCKET_LOG = 'pensive-socket.log'
PENSIVE_PLUGIN_LOG = 'pensive-plugin.log'


def calculate_offset(line_offset, colnum):
    return int(line_offset) + int(colnum) - 1


class SocketClientThread(threading.Thread):
    def __init__(self, vim, input_queue, output_queue, project_dir):
        super(SocketClientThread, self).__init__()
        self.plugin_dir = os.path.dirname(os.path.realpath(__file__))
        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(
            logging.FileHandler(
                os.path.join(self.plugin_dir, PENSIVE_SOCKET_LOG), 'w')
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
                i, o, e = select.select([self.socket], [], [], 0)
                # self.logger.debug('input from select %s' % str(i))
                for s in i:
                    if s == self.socket:
                        self._recv(None)

                (cmd, data) = self.input_queue.get(True, 0.1)
                self.logger.debug('cmd: %s' % cmd)
                self.logger.debug('data: %s' % data)
                self.handlers[cmd](data)
            except Queue.Empty:
                # self.logger.debug('empty queue exception')
                continue
            except Exception as e:
                self.logger.debug("other exception: %s" % str(e))
                continue

    def _send(self, command):
        command_name = command.pop('__name__')
        wrapped_command = json.dumps(
            {"callId": self.command_counter, "req": command}
        )
        request = "{0}{1}".format(
            "%06x" % len(wrapped_command), wrapped_command
        )
        self.logger.debug(request)
        self.socket.send(request)
        self.history[self.command_counter] = command_name
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

    def _update(self):
        self.logger.debug('calling update')
        result = self.output_queue.get()
        self.logger.debug('output queue result: %s' % str(result))
        # output_buffer = [
        #     b for b in self.vim.buffers if b.name.endswith("pensive")
        # ][0]
        parsed_command = json.loads(result)
        command_id = None
        command_type = parsed_command['typehint']
        if command_type == 'RpcResponseEnvelope':
            command_id = parsed_command['callId']

        command = None
        if command_id is not None:
            self.logger.debug('found comand with id: %d' % command_id)
            command_name = self.history[command_id]
            self.logger.debug(
                'command id (%d) matched with command name: (%s)' % (
                    command_id, command_name
                )
            )
            # output_buffer.append('command_name: %s' % command_name)
            command = getattr(ensime, command_name)()

        output = result

        try:
            if getattr(command, 'response', None):
                command.response(
                    parsed_command['payload']
                ).run(self.vim)
            else:
                ensime.Notification.fromJson(
                    parsed_command
                ).run(self.vim)

        except Exception as e:
            self.logger.debug(str(e))
            # output_buffer.append(str(e))

        # output_buffer.append(result)
        # output_buffer.append(output)

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
        threading.Thread.join(self, timeout)


@neovim.plugin
class EnsimePlugin(object):
    def __init__(self, vim):
        self.vim = vim
        self.project_dir = os.path.abspath(os.path.curdir)
        self.plugin_dir = os.path.dirname(os.path.realpath(__file__))
        self.input_queue = Queue.Queue()
        self.output_queue = Queue.Queue()

        self.logger = logging.getLogger(str(self.__class__))
        self.logger.addHandler(
            logging.FileHandler(
                os.path.join(self.plugin_dir, PENSIVE_PLUGIN_LOG), 'w')
        )
        self.logger.level = logging.DEBUG

    @neovim.command("EnsimeStart")
    def command_ensime_start(self):

        start_script_path = os.path.join(self.plugin_dir, 'serverStart.sh')
        ensime_var = 'ENSIME_CONFIG=%s' % os.path.join(
            self.project_dir, '.ensime'
        )
        start_command = "%s %s" % (ensime_var, start_script_path)
        self.logger.debug(start_command)

        self.vim.command("botright new")
        self.vim.command("call termopen([&sh, &shcf, '%s'])" % start_command)

    @neovim.command("EnsimeConnect")
    def command_ensime_connect(self):
        # has_pensive_buffer = len(
        #     [b.name for b in self.vim.buffers if b.name.endswith("pensive")]
        # ) > 0
        # if not has_pensive_buffer:
        #     self.vim.command("new pensive")
        #     self.vim.command("resize 10")
        #     self.vim.command("setlocal buftype=nofile")
        #     self.vim.command("setlocal bufhidden=hide")
        #     self.vim.command("setlocal noswapfile")
        #     self.vim.command("setlocal filetype=scala")

        self.client = SocketClientThread(
            self.vim,
            self.input_queue,
            self.output_queue,
            self.project_dir
        )
        self.client.start()

    @neovim.command("EnsimeUnloadAll", sync=True)
    def command_unload_all(self):
        command = ensime.UnloadAll().request()
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeTypecheckAll", sync=True)
    def command_typecheck_all(self):
        command = ensime.TypecheckAll().request()
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeTypecheckFile", sync=True)
    def command_typecheck_file(self):
        filename = self.vim.current.buffer.name
        command = ensime.TypecheckFile().request(filename)
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeTypeAtPoint", sync=False)
    def command_type_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = ensime.TypeAtPoint().request(
            filename, calculate_offset(line_byte_pos, col_number))
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeSymbolAtPoint", sync=False)
    def command_symbol_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = ensime.SymbolAtPoint().request(
            filename, calculate_offset(line_byte_pos, col_number)
        )
        self.logger.debug(command)
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeUsesOfSymbolAtPoint", sync=False)
    def command_uses_of_symbol_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = ensime.UsesOfSymbolAtPoint().request(
            filename, calculate_offset(line_byte_pos, col_number)
        )
        self.logger.debug(command)
        self.input_queue.put(('send', command))

    @neovim.command("EnsimeImplicitInfo", sync=False)
    def command_implicit_info(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        start = self.vim.eval('line2byte({0})'.format(line_number))
        end = start + len(self.vim.current.line) - 1
        command = ensime.ImplicitInfo().request(
            filename, start, end
        )
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
