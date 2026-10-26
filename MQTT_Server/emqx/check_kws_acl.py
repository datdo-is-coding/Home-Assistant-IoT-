"""Read-only ACL checks using the running EMQX rule evaluator (no MQTT messages)."""
import argparse
import shlex
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--ssh', required=True)
parser.add_argument('--acl', required=True, choices=['/opt/emqx/etc/acl.conf', '/tmp/kws-acl-candidate.conf', '/opt/emqx/data/authz/local-kws-acl.conf'])
args = parser.parse_args()
checks = [
    ('SB288485350B54', 'publish', 'home/subbox/SB288485350B54/event/kws_result', 'allow'),
    ('SB288485350B54', 'publish', 'home/subbox/SB111111111111/event/kws_result', 'deny'),
    ('SB288485350B54', 'publish', 'home/subbox/SB111111111111/event/kws_config', 'deny'),
    ('SB288485350B54', 'publish', 'home/subbox/SB288485350B54/command', 'deny'),
    ('SB288485350B54', 'subscribe', 'home/subbox/SB288485350B54/command', 'allow'),
    ('SB288485350B54', 'subscribe', 'home/kws/+/SB288485350B54/command', 'allow'),
    ('SB288485350B54', 'subscribe', 'home/kws/+/SB111111111111/command', 'deny'),
    ('SB288485350B54', 'publish', 'home/kws/SB111111111111/SB288485350B54/command', 'deny'),
    ('SB288485350B54', 'publish', 'home/kws/SB288485350B54/SB111111111111/command', 'deny'),
    ('SB288485350B54', 'publish', 'home/kws/SB111111111111/SB288485350B54/ack', 'deny'),
    ('smarthome_gateway', 'publish', 'home/subbox/SB288485350B54/command', 'allow'),
    ('smarthome_gateway', 'subscribe', 'home/subbox/+/event/kws_result', 'allow'),
    ('SB288485350B54', 'publish', 'home/subbox/SB288485350B54/event/actionbox', 'allow'),
]
expression = f'{{ok, Terms}}=file:consult("{args.acl}"), Rules=[emqx_authz_rule:compile(T) || T <- Terms], '
for user, action, topic, expected in checks:
    expression += (f'{{matched,{expected}}}=emqx_authz_rule:matches('
                   f'#{{username=><<"{user}">>,clientid=><<"{user}">>,peerhost=>{{192,168,11,159}}}},'
                   f'#{{action_type=>{action},qos=>1,retain=>false}},<<"{topic}">>,Rules), ')
expression += 'io:format("KWS_ACL_CHECKS_OK~n").'
command = shlex.join(['docker', 'exec', 'emqx_broker', 'emqx', 'eval', expression])
run = subprocess.run(['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=7', args.ssh, command], capture_output=True, text=True, timeout=30)
if run.returncode or 'KWS_ACL_CHECKS_OK' not in run.stdout:
    raise SystemExit('ACL checks failed: ' + run.stdout + run.stderr)
print(f'{len(checks)} EMQX ACL checks passed ({args.acl})')
