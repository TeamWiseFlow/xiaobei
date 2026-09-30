"""PK event decoding and bounded lifecycle correlation."""

from collections import OrderedDict
from .proto import PK_pb2

PK_MESSAGES = {
    "LinkMicMethod": PK_pb2.LinkMicMethod,
    "LinkMicArmiesMethod": PK_pb2.LinkMicArmies,
    "LinkMicBattleMethod": PK_pb2.LinkMicBattle,
    "LinkMicBattleFinishMethod": PK_pb2.LinkMicBattleFinish,
}


def _id(number, explicit=""):
    return explicit or (str(number) if number else None)


def _time_ms(value):
    return value * 1000 if 0 < value < 100000000000 else value


def _ranks(users):
    return [
        dict(
            rank=index,
            uid=_id(u.user_id, getattr(u, "user_id_str", "")),
            nickname=u.nickname,
            score=str(u.score),
        )
        for index, u in enumerate(users, 1)
    ]


def _scores(users):
    return [
        dict(
            anchor_id=_id(u.user_id, u.user_id_str),
            score=str(u.score),
            score_blur_text=u.score_blur_text,
            score_relative_text=u.score_relative_text,
            battle_rank=int(u.battle_rank),
        )
        for u in users
    ]


def decode_pk_message(method, payload, msg_id=0):
    canonical = method.removeprefix("Webcast")
    cls = PK_MESSAGES.get(canonical)
    if cls is None:
        return None
    message = cls.FromString(payload)
    event = dict(
        method=method,
        msg_id=_id(msg_id or message.common.msg_id),
        room_id=_id(message.common.room_id),
        create_time_ms=_time_ms(message.common.create_time),
        battle_id=None,
        channel_id=None,
        context_battle_id=None,
        context_channel_id=None,
    )
    if canonical == "LinkMicMethod":
        if message.message_type != 202:
            return None
        event.update(
            type="scores",
            battle_id=_id(message.battle_id, message.battle_id_str),
            channel_id=_id(message.channel_id),
            scores=_scores(message.user_scores),
        )
    elif canonical == "LinkMicArmiesMethod":
        event.update(
            type="armies",
            is_complete=False,
            anchors=[
                dict(anchor_id=str(anchor), users=_ranks(army.user_armies))
                for anchor, army in sorted(message.user_armies_map.items())
            ],
            unassigned_armies=[
                _ranks(army.user_armies) for army in message.user_armies_list
            ],
            has_unsupported_rank_list_v2=bool(message.rank_list_v2),
        )
    else:
        settings = message.battle_settings
        event.update(
            battle_id=_id(settings.battle_id, settings.battle_id_str),
            channel_id=_id(settings.channel_id, settings.channel_id_str),
            start_time_ms=settings.start_time_ms,
            duration=int(settings.duration),
            battle_status=int(settings.battle_status),
        )
        if canonical == "LinkMicBattleFinishMethod":
            event.update(
                type="finish",
                is_complete=False,
                end_reason=message.end_reason,
                scores=_scores(message.battle_scores),
                anchors=[
                    dict(
                        anchor_id=_id(army.anchor_id, army.anchor_id_str),
                        users=_ranks(army.rank_list),
                    )
                    for army in message.battle_armies
                ],
            )
        else:
            event["type"] = "start" if settings.battle_status == 1 else "status"
    return event


class PKMessageHandler:
    def __init__(self):
        self.active = None
        self._seen = OrderedDict()
        self._finished = OrderedDict()

    @staticmethod
    def _remember(cache, key, limit=512):
        duplicate = key in cache
        cache[key] = None
        cache.move_to_end(key)
        if len(cache) > limit:
            cache.popitem(last=False)
        return duplicate

    def handle(self, method, payload, msg_id=0):
        event = decode_pk_message(method, payload, msg_id)
        if event is None:
            return None
        if event["msg_id"] and self._remember(
            self._seen, (method.removeprefix("Webcast"), event["msg_id"])
        ):
            return None
        kind, battle_id = (event["type"], event["battle_id"])
        if kind == "finish":
            finish_key = (
                battle_id,
                repr(sorted(event["scores"], key=lambda s: s["anchor_id"] or "")),
                repr(sorted(event["anchors"], key=lambda a: a["anchor_id"] or "")),
                event["end_reason"],
            )
            if battle_id and self._remember(self._seen, finish_key):
                return None
            if battle_id:
                self._remember(self._finished, battle_id, limit=128)
            if self.active and battle_id == self.active["battle_id"]:
                self.active = None
        elif (
            kind in ("start", "scores")
            and battle_id
            and (battle_id not in self._finished)
        ):
            since = event.get("start_time_ms") or event["create_time_ms"]
            same_battle = self.active and battle_id == self.active["battle_id"]
            if same_battle:
                self.active["channel_id"] = (
                    event["channel_id"] or self.active["channel_id"]
                )
            elif not self.active or (since and since >= self.active["since"]):
                self.active = dict(
                    battle_id=battle_id, channel_id=event["channel_id"], since=since
                )
        elif (
            kind == "status" and self.active and (battle_id == self.active["battle_id"])
        ):
            if event["battle_status"] in (2, 3):
                self.active = None
        elif kind == "armies" and self.active:
            since, created = (self.active["since"], event["create_time_ms"])
            if since and created and (created >= since):
                event["context_battle_id"] = self.active["battle_id"]
                event["context_channel_id"] = self.active["channel_id"]
        return event
