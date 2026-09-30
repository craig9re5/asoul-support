"""One policy-to-command adapter for desktop and scheduled script workers."""


def watch_arguments(member, policy):
    argv = ["--until-offline", "--members", member["name"]]
    flags = (("auto_revive", "--no-revive"), ("auto_danmaku_intimacy", "--no-intimacy-danmaku"))
    argv.extend(flag for key, flag in flags if not policy.get(key, True))
    if not policy.get("auto_revive", True) and not policy.get("auto_danmaku_intimacy", True):
        argv.append("--no-danmaku")
    if policy.get("auto_like", False):
        argv.append("--live-likes")
    return argv
