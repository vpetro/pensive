import json
import os.path
from threading import Thread
from websocket import create_connection
import Queue
import neovim
import ensime
import logging

PENSIVE_SOCKET_LOG = 'pensive.log'


def calculate_offset(line_offset, colnum):
    return int(line_offset) + int(colnum) - 1


@neovim.plugin
class EnsimeClient(object):
    def __init__(self, vim):
        self.vim = vim
        self.plugin_dir = os.path.dirname(os.path.realpath(__file__))
        self.project_dir = os.path.abspath(os.path.curdir)
        self.is_running = False
        self.ws = None
        self.thread = None
        self.queue = Queue.Queue()
        self.call_id = 0
        self.history = {}

        self.logger = logging.getLogger(__name__)
        self.logger.addHandler(
            logging.FileHandler(
                os.path.join(self.plugin_dir, PENSIVE_SOCKET_LOG), 'w')
        )
        self.logger.level = logging.DEBUG

    @neovim.command("EnsimeConnect")
    def connect(self):
        if not self.is_running:
            self.port = int(open(
                os.path.join(self.project_dir, ".ensime_cache/http"), "r"
            ).read().strip())
            self.url = "ws://127.0.0.1:{}/websocket".format(self.port)
            self.options = {
                'subprotocols': ['jerky'],
                'enable_multithread': True
            }
            self.ws = create_connection(
                self.url,
                **self.options
            )
            self.is_running = True
            self.thread = Thread(
                name='recv',
                target=self.recv)
            self.thread.daemon = True
            self.thread.start()
            self.send(ensime.ConnectionInfo().request())
        else:
            self.logger.debug("attempted to start while already running")
            pass
            print 'already running'

    def send(self, message):
        self.call_id += 1
        filtered_message = {
            k: v for k, v in message.iteritems()
        }

        command_name = filtered_message.pop('__name__')
        payload = {
            'callId': self.call_id,
            'req': filtered_message
        }
        self.history[self.call_id] = command_name
        self.ws.send(json.dumps(payload))
        return message

    def recv(self):
        while self.is_running:
            try:
                message = self.ws.recv()
                parsed = json.loads(message)
                self.queue.put(parsed)
                self.vim.session.threadsafe_call(self.update)
            except Exception as e:
                self.logger.debug("recv exception: %s" % str(e))

    def update(self):
        try:
            result = self.queue.get(True, 0.1)
            self.logger.debug("receive: %s" % json.dumps(result))
            call_id = result.get('callId')
            if call_id is not None:
                command_name = self.history[call_id]
                self.logger.debug("command_name: %s" % str(command_name))
                command = getattr(ensime, command_name)()
                self.logger.debug("command: %s" % str(command))

                if getattr(command, 'response', None):
                    self.logger.debug("command: executing response")
                    command.response(
                        result['payload']
                    ).run(self.vim)
                    self.logger.debug("command: executed response")
                else:
                    self.logger("Warning: command has no 'response'")
            else:
                ensime.Notification.fromJson(
                    result['payload']
                ).run(self.vim)

        except Queue.Empty:
            pass
        except Exception as e:
            self.logger.debug("update exception: %s" % str(e))
        return result

    @neovim.command("EnsimeConnectionInfo", sync=True)
    def command_connection_info(self):
        command = ensime.ConnectionInfo().request()
        self.send(command)

    @neovim.command("EnsimeTypecheckFile", sync=True)
    def command_typecheck_file(self):
        filename = self.vim.current.buffer.name
        command = ensime.TypecheckFile().request(filename)
        self.send(command)

    @neovim.command("EnsimeTypeAtPoint", sync=False)
    def command_type_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = ensime.TypeAtPoint().request(
            filename, calculate_offset(line_byte_pos, col_number))
        self.send(command)

    @neovim.command("EnsimeTypeOfSelection", sync=False)
    def command_type_of_selection(self):
        filename = self.vim.current.buffer.name
        start_line_number, start_col_number = self.vim.eval(
            'getpos("\'<")')[1:3]
        end_line_number, end_col_number = self.vim.eval('getpos("\'>")')[1:3]
        start_line_byte_pos = self.vim.eval('line2byte({0})'.format(
            start_line_number))
        end_line_byte_pos = self.vim.eval('line2byte({0})'.format(
            end_line_number))
        command = ensime.TypeOfSelection().request(
            filename,
            calculate_offset(start_line_byte_pos, start_col_number),
            calculate_offset(end_line_byte_pos, end_col_number - 1))
        self.send(command)

    @neovim.command("EnsimeSymbolAtPoint", sync=False)
    def command_symbol_at_point(self):
        filename = self.vim.current.buffer.name
        line_number, col_number = self.vim.eval('getpos(".")')[1:3]
        line_byte_pos = self.vim.eval('line2byte({0})'.format(line_number))
        command = ensime.SymbolAtPoint().request(
            filename, calculate_offset(line_byte_pos, col_number)
        )
        self.logger.debug('sending: %s' % json.dumps(command))
        self.send(command)


def main():
    project_dir = '/Users/petrov/work/internal/bamboo-openair'
    import neovim
    vim = neovim.attach('socket', path='/tmp/v')
    client = EnsimeClient(project_dir, vim)
    client.connect()
    return client
