"""Strict customer policy validation and installation windows."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re


class OtaError(Exception):
    def __init__(self, code, status=409):
        super().__init__(code)
        self.code, self.status = code, status


def require(condition, code, status=409):
    if not condition:
        raise OtaError(code, status)


def fields(body, allowed, required=()):
    require(isinstance(body, dict) and set(body) <= set(allowed) and set(required) <= set(body), 'invalid_fields', 400)


def identifier(value):
    require(isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value) is not None, 'invalid_id', 400)
    return value


def digest(value):
    require(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value) is not None, 'invalid_digest', 400)
    return value


def integer(value, low, high):
    require(type(value) is int and low <= value <= high, 'invalid_integer', 400)
    return value


def validate_policy(body):
    fields(body, ('revision', 'consent', 'timezone', 'start_minute', 'end_minute', 'days', 'excluded_targets', 'hold_until'), ('revision', 'consent', 'timezone', 'start_minute', 'end_minute', 'days', 'excluded_targets'))
    integer(body['revision'], 0, 2**53 - 1)
    require(type(body['consent']) is bool, 'invalid_consent', 400)
    require(isinstance(body['timezone'], str), 'invalid_timezone', 400)
    try:
        ZoneInfo(body['timezone'])
    except (ValueError, ZoneInfoNotFoundError):
        raise OtaError('invalid_timezone', 400)
    integer(body['start_minute'], 0, 1439)
    integer(body['end_minute'], 0, 1439)
    require(isinstance(body['days'], list) and 0 < len(body['days']) <= 7, 'invalid_days', 400)
    for day in body['days']:
        integer(day, 0, 6)
    require(len(set(body['days'])) == len(body['days']), 'invalid_days', 400)
    require(isinstance(body['excluded_targets'], list) and len(body['excluded_targets']) <= 256, 'invalid_exclusions', 400)
    for target in body['excluded_targets']:
        identifier(target)
    integer(body.get('hold_until', 0), 0, 2**53 - 1)
    return dict(body, revision=body['revision'] + 1)


def may_install(policy, target_id, now):
    if not policy.get('consent') or target_id in policy.get('excluded_targets', []) or now < policy.get('hold_until', 0):
        return False
    local = datetime.fromtimestamp(now, timezone.utc).astimezone(ZoneInfo(policy['timezone']))
    minute = local.hour * 60 + local.minute
    start, end = policy['start_minute'], policy['end_minute']
    if start == end:
        return local.weekday() in policy['days']
    if start < end:
        return local.weekday() in policy['days'] and start <= minute < end
    if minute >= start:
        return local.weekday() in policy['days']
    return minute < end and (local - timedelta(days=1)).weekday() in policy['days']
