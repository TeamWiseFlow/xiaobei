"""Generated platform protocol codec."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x08PK.proto\x12\tdouyin.pk"N\n\x06Common\x12\x0e\n\x06method\x18\x01 \x01(\t\x12\x0e\n\x06msg_id\x18\x02 \x01(\x03\x12\x0f\n\x07room_id\x18\x03 \x01(\x03\x12\x13\n\x0bcreate_time\x18\x04 \x01(\x03"\xa6\x01\n\x0eBattleSettings\x12\x11\n\tbattle_id\x18\x02 \x01(\x03\x12\x15\n\rstart_time_ms\x18\x03 \x01(\x03\x12\x10\n\x08duration\x18\x04 \x01(\x03\x12\x12\n\nchannel_id\x18\x06 \x01(\x03\x12\x15\n\rbattle_status\x18( \x01(\x03\x12\x15\n\rbattle_id_str\x18* \x01(\t\x12\x16\n\x0echannel_id_str\x18+ \x01(\t"<\n\x08UserArmy\x12\x0f\n\x07user_id\x18\x01 \x01(\x03\x12\r\n\x05score\x18\x02 \x01(\x03\x12\x10\n\x08nickname\x18\x03 \x01(\t"6\n\nUserArmies\x12(\n\x0buser_armies\x18\x01 \x03(\x0b2\x13.douyin.pk.UserArmy"\x8c\x02\n\rLinkMicArmies\x12!\n\x06common\x18\x01 \x01(\x0b2\x11.douyin.pk.Common\x12D\n\x0fuser_armies_map\x18\x02 \x03(\x0b2+.douyin.pk.LinkMicArmies.UserArmiesMapEntry\x12/\n\x10user_armies_list\x18\x03 \x03(\x0b2\x15.douyin.pk.UserArmies\x12\x14\n\x0crank_list_v2\x18\x04 \x01(\x0c\x1aK\n\x12UserArmiesMapEntry\x12\x0b\n\x03key\x18\x01 \x01(\x03\x12$\n\x05value\x18\x02 \x01(\x0b2\x15.douyin.pk.UserArmies:\x028\x01"\x8c\x01\n\nUserScores\x12\r\n\x05score\x18\x01 \x01(\x03\x12\x0f\n\x07user_id\x18\x02 \x01(\x03\x12\x1b\n\x13score_relative_text\x18\x04 \x01(\t\x12\x17\n\x0fscore_blur_text\x18\x07 \x01(\t\x12\x13\n\x0bbattle_rank\x18\x08 \x01(\x03\x12\x13\n\x0buser_id_str\x18\x15 \x01(\t"\xc9\x01\n\rLinkMicMethod\x12!\n\x06common\x18\x01 \x01(\x0b2\x11.douyin.pk.Common\x12\x14\n\x0cmessage_type\x18\x02 \x01(\x03\x12\x12\n\nchannel_id\x18\x08 \x01(\x03\x12\x15\n\rstart_time_ms\x18\x1a \x01(\x03\x12*\n\x0buser_scores\x18\x11 \x03(\x0b2\x15.douyin.pk.UserScores\x12\x11\n\tbattle_id\x18h \x01(\x03\x12\x15\n\rbattle_id_str\x18r \x01(\t"f\n\rLinkMicBattle\x12!\n\x06common\x18\x01 \x01(\x0b2\x11.douyin.pk.Common\x122\n\x0fbattle_settings\x18\x02 \x01(\x0b2\x19.douyin.pk.BattleSettings"Q\n\x08RankUser\x12\x0f\n\x07user_id\x18\x01 \x01(\x03\x12\x10\n\x08nickname\x18\x02 \x01(\t\x12\r\n\x05score\x18\x04 \x01(\x03\x12\x13\n\x0buser_id_str\x18\x05 \x01(\t"^\n\nBattleArmy\x12\x11\n\tanchor_id\x18\x01 \x01(\x03\x12&\n\trank_list\x18\x02 \x03(\x0b2\x13.douyin.pk.RankUser\x12\x15\n\ranchor_id_str\x18\x03 \x01(\t"\x8d\x01\n\x0bBattleScore\x12\r\n\x05score\x18\x01 \x01(\x05\x12\x0f\n\x07user_id\x18\x02 \x01(\x03\x12\x13\n\x0buser_id_str\x18\x08 \x01(\t\x12\x1b\n\x13score_relative_text\x18\x0c \x01(\t\x12\x17\n\x0fscore_blur_text\x18\x0f \x01(\t\x12\x13\n\x0bbattle_rank\x18\x10 \x01(\x03"\xdd\x01\n\x13LinkMicBattleFinish\x12!\n\x06common\x18\x01 \x01(\x0b2\x11.douyin.pk.Common\x122\n\x0fbattle_settings\x18\x02 \x01(\x0b2\x19.douyin.pk.BattleSettings\x12,\n\rbattle_armies\x18\x03 \x03(\x0b2\x15.douyin.pk.BattleArmy\x12-\n\rbattle_scores\x18\x04 \x03(\x0b2\x16.douyin.pk.BattleScore\x12\x12\n\nend_reason\x18\x08 \x01(\x05b\x06proto3')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, __name__, _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _globals['_LINKMICARMIES_USERARMIESMAPENTRY']._options = None
    _globals['_LINKMICARMIES_USERARMIESMAPENTRY']._serialized_options = b'8\x01'
    _globals['_COMMON']._serialized_start = 23
    _globals['_COMMON']._serialized_end = 101
    _globals['_BATTLESETTINGS']._serialized_start = 104
    _globals['_BATTLESETTINGS']._serialized_end = 270
    _globals['_USERARMY']._serialized_start = 272
    _globals['_USERARMY']._serialized_end = 332
    _globals['_USERARMIES']._serialized_start = 334
    _globals['_USERARMIES']._serialized_end = 388
    _globals['_LINKMICARMIES']._serialized_start = 391
    _globals['_LINKMICARMIES']._serialized_end = 659
    _globals['_LINKMICARMIES_USERARMIESMAPENTRY']._serialized_start = 584
    _globals['_LINKMICARMIES_USERARMIESMAPENTRY']._serialized_end = 659
    _globals['_USERSCORES']._serialized_start = 662
    _globals['_USERSCORES']._serialized_end = 802
    _globals['_LINKMICMETHOD']._serialized_start = 805
    _globals['_LINKMICMETHOD']._serialized_end = 1006
    _globals['_LINKMICBATTLE']._serialized_start = 1008
    _globals['_LINKMICBATTLE']._serialized_end = 1110
    _globals['_RANKUSER']._serialized_start = 1112
    _globals['_RANKUSER']._serialized_end = 1193
    _globals['_BATTLEARMY']._serialized_start = 1195
    _globals['_BATTLEARMY']._serialized_end = 1289
    _globals['_BATTLESCORE']._serialized_start = 1292
    _globals['_BATTLESCORE']._serialized_end = 1433
    _globals['_LINKMICBATTLEFINISH']._serialized_start = 1436
    _globals['_LINKMICBATTLEFINISH']._serialized_end = 1657
