"""Generated platform protocol codec."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import runtime_version as _runtime_version
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_runtime_version.ValidateProtobufRuntimeVersion(_runtime_version.Domain.PUBLIC, 5, 27, 1, '', 'Response.proto')
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x0eResponse.proto"\x82\x01\n\x08Response\x12\x0b\n\x03cmd\x18\x01 \x01(\x05\x12\x13\n\x0bsequence_id\x18\x02 \x01(\x03\x12\x12\n\nerror_desc\x18\x03 \x01(\t\x12\x0f\n\x07message\x18\x04 \x01(\t\x12\x12\n\ninbox_type\x18\x05 \x01(\x03\x12\x1b\n\x04body\x18\x06 \x01(\x0b2\r.ResponseBody"\xf8\x01\n\x0cResponseBody\x120\n\x12new_message_notify\x18\xf4\x03 \x01(\x0b2\x11.NewMessageNotifyH\x00\x12N\n\x1bcreate_conversation_v2_body\x18\xe1\x04 \x01(\x0b2&.GetConversationInfoListV2ResponseBodyH\x00\x12^\n+get_conversation_info_list_v2_response_body\x18\xe2\x04 \x01(\x0b2&.GetConversationInfoListV2ResponseBodyH\x00B\x06\n\x04body"z\n\x10NewMessageNotify\x12\x17\n\x0fconversation_id\x18\x02 \x01(\t\x12\x19\n\x11conversation_type\x18\x03 \x01(\x05\x12\x13\n\x0bnotify_type\x18\x04 \x01(\x05\x12\x1d\n\x07message\x18\x05 \x01(\x0b2\x0c.MessageBody"\xd1\x01\n\x0bMessageBody\x12\x17\n\x0fconversation_id\x18\x01 \x01(\t\x12\x19\n\x11conversation_type\x18\x02 \x01(\x05\x12\x19\n\x11server_message_id\x18\x03 \x01(\x03\x12\x1d\n\x15index_in_conversation\x18\x04 \x01(\x03\x12\x1d\n\x15conversation_short_id\x18\x05 \x01(\x03\x12\x14\n\x0cmessage_type\x18\x06 \x01(\x05\x12\x0e\n\x06sender\x18\x07 \x01(\x03\x12\x0f\n\x07content\x18\x08 \x01(\t"g\n%GetConversationInfoListV2ResponseBody\x12>\n\x16conversation_info_list\x18\x01 \x03(\x0b2\x1e.GetConversationInfoV2Response"\x82\x01\n\x1dGetConversationInfoV2Response\x12\x17\n\x0fconversation_id\x18\x01 \x01(\t\x12\x1d\n\x15conversation_short_id\x18\x02 \x01(\x03\x12\x19\n\x11conversation_type\x18\x03 \x01(\x05\x12\x0e\n\x06ticket\x18\x04 \x01(\tb\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, __name__, _globals)
if not _descriptor._USE_C_DESCRIPTORS:
    DESCRIPTOR._loaded_options = None
    _globals['_RESPONSE']._serialized_start = 19
    _globals['_RESPONSE']._serialized_end = 149
    _globals['_RESPONSEBODY']._serialized_start = 152
    _globals['_RESPONSEBODY']._serialized_end = 400
    _globals['_NEWMESSAGENOTIFY']._serialized_start = 402
    _globals['_NEWMESSAGENOTIFY']._serialized_end = 524
    _globals['_MESSAGEBODY']._serialized_start = 527
    _globals['_MESSAGEBODY']._serialized_end = 736
    _globals['_GETCONVERSATIONINFOLISTV2RESPONSEBODY']._serialized_start = 738
    _globals['_GETCONVERSATIONINFOLISTV2RESPONSEBODY']._serialized_end = 841
    _globals['_GETCONVERSATIONINFOV2RESPONSE']._serialized_start = 844
    _globals['_GETCONVERSATIONINFOV2RESPONSE']._serialized_end = 974
