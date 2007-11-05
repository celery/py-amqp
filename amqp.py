"""
AMQP Library

2007-11-05 Barry Pederson <bp@barryp.org>

"""
import socket
from struct import pack, unpack
try:
    from cStringIO import StringIO
except:
    from StringIO import StringIO


AMQP_PORT = 5672
AMQP_PROTOCOL_HEADER = 'AMQP\x01\x01\x09\x01'

class _MethodArgs(object):
    def __init__(self, payload):
        x = 10
        self.input = StringIO(payload)
        
    def read_octet(self):
        return unpack('B', self.input.read(1))[0]
    def read_short(self):
        return unpack('>H', self.input.read(2))[0]
    def read_long(self):
        return unpack('>I', self.input.read(4))[0]
    def read_longlong(self):
        return unpack('>Q', self.input.read(8))[0]
    def read_shortstr(self):
        len = unpack('B', self.input.read(1))[0]
        return self.input.read(len).decode('utf-8')
    def read_longstr(self):
        len = unpack('>I', self.input.read(4))[0]
        return self.input.read(len)
    def read_table(self):
        len = unpack('>I', self.input.read(4))[0]
        table_data = _MethodArgs(self.input.read(len))
        result = {}
        while table_data.input.tell() < len:
            name = table_data.read_shortstr()
            ftype = table_data.input.read(1)
            if ftype == 'S':
                val = table_data.read_longstr()
            elif ftype == 'I':
                val = unpack('i', table_data.input.read(4))[0]
            elif ftype == 'D':
                d = table_data.read_octet()
                n = table_data.read_long()
                val = decimal(n) / decimal(10 ** d)
            elif ftype == 'T':
                val = table_data.read_longlong()
            elif ftype == 'F':
                val = table_data.read_table() # recurse
            result[name] = val
        return result
                

class Connection(object):
    """
    An AMQP Connection

    """
    
    def __init__(self):
        self.channels = {}
        self.input = self.out = None

    def __delete__(self):
        if self.input:
            self.close(msg='destroying connection')

    def channel(self, channel_num):
        if channel_num in self.channels:
            return self.channels[channel_num]
        self.channels[channel_num] = ch = Channel(self, channel_num)
        return ch

    def close(self, msg=''):
        for ch in list(self.channels.values()):
            ch.close(msg)
        self.input = self.out = None
        
    def open(self, host):
        if ':' in host:
            host, port = host.split(':', 1)
            port = int(port)
        else:
            port = AMQP_PORT
            
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((host, port))
        self.input = sock.makefile('r')
        self.out = sock.makefile('w')
        self.out.write(AMQP_PROTOCOL_HEADER)
        self.out.flush()
        self.wait()
       
    def start(self, args):
        version_major = args.read_octet()
        version_minor = args.read_octet()
        properties = args.read_table()
        mechanisms = args.read_longstr()
        locales = args.read_longstr()
        print 'Start from server: %d.%d, properties: %s, mech: %s, locales: %s' % (version_major, version_minor, str(properties), mechanisms, locales)
        
       
    def wait(self):
        """
        Wait for a frame from the server
        
        """
        s = self.input.read(7)
        for ch in s: print hex(ord(ch)),
        print ''
        frame_type, channel, size = unpack('!BHI', s)
        print 'frame_type: %d, channel: %d, size: %d' % (frame_type, channel, size)
        payload = self.input.read(size)

        ch = self.input.read(1)
        if ch != '\xce':
            raise Exception('Framing error, unexpected byte: %x' % ord(ch))
        
        if frame_type == 1:
            dispatch_method(self, channel, payload)
        

class Channel(object):
    def __init__(self, connection, channel_num):
        self.connection = connection
        self.channel_num = channel_num

    def __delete__(self):
        if self.connection:
            self.close(msg='destroying channel')

    def close(self, msg=''):
        del self.connection.channels[self.channel_num]
        self.connection = None
        
        
def dispatch_method(connection, channel, payload):
    if len(payload) < 4:
        raise Exception('Method frame too short')
    class_id, method_id = unpack('>HH', payload[:4])
    args = _MethodArgs(payload[4:])
   
    if class_id == 10 and method_id == 10:
        connection.start(args)
    else:
        print 'unknown:', class_id, method_id
        
        
        
AMQP_METHODS = {
    10: {
        10: Connection.start,
        },
    20: {
        },
    }
    


def main():
    conn = Connection()
    conn.open('10.66.0.8')
    ch = conn.channel(1)
#    ch.basic_publish('hello world')
    
if __name__ == '__main__':
    main()
