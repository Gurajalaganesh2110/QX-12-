"""Binary frames used by the TNY-360 app/SDK (little-endian).
Request : type=1, flags, msg_id(u16), module(u8), action(u8), length(u16), payload
Response: type=2, flags, msg_id(u16), status(u16), length(u16), payload
flags bit0 = sender wants a reply."""
import struct

REQ = struct.Struct("<BBHBBH")
RES = struct.Struct("<BBHHH")
ACK = 1
OK, UNKNOWN_MODULE, UNKNOWN_ACTION, INVALID_PARAMS = 0, 1, 2, 3

# Modules that already exist in the TNY SDK
SYSTEM, GAIT, BODY, ERROR, DIAGNOSTIC = 0, 2, 3, 19, 20
# Our own modules (IDs >= 32 so they never clash)
HEAD, DISTANCE, ARM, ACTION, SELFTEST = 32, 33, 34, 35, 36

def pack_request(msg_id, module, action, payload=b"", ack=True):
    return REQ.pack(1, ACK if ack else 0, msg_id, module, action, len(payload)) + payload

def parse_request(data):
    _, flags, msg_id, module, action, n = REQ.unpack_from(data)
    return flags, msg_id, module, action, data[REQ.size:REQ.size + n]

def pack_response(msg_id, status=OK, payload=b""):
    return RES.pack(2, 0, msg_id, status, len(payload)) + payload

def parse_response(data):
    _, _, msg_id, status, n = RES.unpack_from(data)
    return msg_id, status, data[RES.size:RES.size + n]

def f32(*v): return struct.pack(f"<{len(v)}f", *v)
def string(s): b = s.encode(); return struct.pack("<H", len(b)) + b
def read_string(p): n = struct.unpack_from("<H", p)[0]; return p[2:2 + n].decode()
