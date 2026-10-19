"""Existing VM SSH forwarding rules, independent of performance campaigns."""

SSH_RULE = "ssh-maintenance,tcp,127.0.0.1,2221,,22"

def nat_rules(info):
    return [line.split("=", 1)[1].strip('"') for line in info.splitlines()
            if line.startswith("Forwarding(")]

def nat_rule_needed(rule, existing):
    desired = rule.split(",")
    for current in existing:
        fields = current.split(",")
        if fields[1:] == desired[1:]:
            return False  # Equivalent forwarding can have a different name.
    for current in existing:
        fields = current.split(",")
        if fields[0] == desired[0] or (fields[1] == desired[1] and fields[3] == desired[3]
                and (fields[2] == desired[2] or not fields[2] or not desired[2])):
            raise RuntimeError(f"Redirection NAT incompatible : {current} ; attendue : {rule}. Règle existante conservée.")
    return True

