"""Small, explicit climate grammar; device/room matching remains server-side."""
import re
from ..voice import normalize

_DIGITS={'mot':1,'moi':1,'hai':2,'ba':3,'bon':4,'tu':4,'nam':5,'lam':5,'sau':6,'bay':7,'tam':8,'chin':9}
_NUMBER=r'(?:[0-9]{1,2}|ba muoi|hai muoi(?: (?:mot|moi|hai|ba|bon|tu|nam|lam|sau|bay|tam|chin))?|muoi(?: (?:sau|bay|tam|chin))?)'

def climate_intent(text):
    if not isinstance(text,str) or not 0<len(text)<=200:return None
    phrase=normalize(text)
    if re.search(r'\b(khong|dung|chua)\b',phrase):return None
    power=re.fullmatch(r'(bat|tat|turn on|turn off) (.+)',phrase)
    if power:return power[2],{'power':power[1] in ('bat','turn on')},'power'
    temperature=re.fullmatch(r'(?:(?:dat|chinh|cai)(?: nhiet do)? |cho )?(.+?) (?:ve |xuong |len |o muc )?('+_NUMBER+r') do(?: c)?',phrase)
    if temperature and not phrase.startswith(('tang ','giam ')):
        value=temperature[2]
        if value.isdecimal():degrees=int(value)
        elif value=='ba muoi':degrees=30
        elif value.startswith('hai muoi'):degrees=20+_DIGITS.get(value[9:],0)
        else:degrees=10+_DIGITS.get(value[5:],0)
        return temperature[1],{'power':True,'temperature':degrees},'temperature'
    relative=re.fullmatch(r'(tang|giam)(?: nhiet do)? (.+?)(?: (?:len|xuong))?(?: ([1-5]|mot|hai|ba|bon|nam) do)?',phrase)
    if relative:
        amount=relative[3] or '1';amount=int(amount) if amount.isdecimal() else _DIGITS[amount]
        return relative[2],{'delta':(1 if relative[1]=='tang' else -1)*amount},'relative'
    return None
