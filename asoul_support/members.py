"""Local list of livestream accounts to monitor and support.

Use the streamer's UID (mid) and real live room ID, which are often different.
DEFAULT_MEMBERS seeds first-run configuration. All entry points then read the
shared members.json using load_members().
"""

DEFAULT_MEMBERS = [
    {"name": "小松绿Viridis", "uid": 1891335475, "room": 1727071052},
    {"name": "泽音Melody", "uid": 1203217682, "room": 1947277414},
    {"name": "凛光暗切", "uid": 20572289, "room": 5233147},
    {"name": "四时小路Komichi", "uid": 1512246445, "room": 1700301235},
    {"name": "灰泽满Hazel", "uid": 1298779265, "room": 1713546334},
]


def load_members(root=None):
    from .runtime import data_dir, read_json

    members = read_json((root or data_dir()) / "members.json", DEFAULT_MEMBERS)
    return validate_members(members)


def validate_members(members):
    if not isinstance(members, list):
        raise ValueError("成员配置必须是 JSON 列表")
    rooms, names = (set(), set())
    for member in members:
        if (
            not isinstance(member, dict)
            or not isinstance(member.get("name"), str)
            or (not member["name"].strip())
            or ("," in member["name"])
            or any((type(member.get(k)) is not int or member[k] <= 0 for k in ("uid", "room")))
        ):
            raise ValueError("成员需要名称、正整数 UID 和房间号，名称不能包含逗号")
        if member["room"] in rooms or member["name"] in names:
            raise ValueError("成员名称和直播间号不能重复")
        rooms.add(member["room"])
        names.add(member["name"])
    return members


MEMBERS = DEFAULT_MEMBERS
