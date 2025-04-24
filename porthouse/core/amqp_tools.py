import requests
from typing import Union, List

def rest_queue_list(user:str='guest', password:str='guest', host='localhost', port=15672, virtual_host=None) -> List[dict]:
    url = 'http://%s:%s/api/queues/%s' % (host, port, virtual_host or '')
    response = requests.get(url, auth=(user, password))
    queues = response.json() #[q['name'] for q in response.json()]
    return queues


def rest_exchange_list(user:str='guest', password:str='guest', host='localhost', port=15672, virtual_host=None) -> List[dict]:
    url = 'http://%s:%s/api/exchanges/%s' % (host, port, virtual_host or '')
    response = requests.get(url, auth=(user, password))
    exchanges = response.json() #[e['name'] for e in response.json()]
    return exchanges



def check_exchange_exists(name:str, exchange_type:str, auto_delete:Union[bool,None]=None, durable:Union[bool,None]=None, amqp_kwargs:Union[dict,None]=None) -> bool:
    if amqp_kwargs:
        exes = rest_exchange_list(**amqp_kwargs)
    else:
        exes = rest_exchange_list()
    for e in exes:
        if e["name"] == name:
            if e["type"] != exchange_type:
                return False
            if not (auto_delete is None):
                if e["auto_delete"] != auto_delete:
                    return False
            if not (durable is None):
                if e["durable"] != durable:
                    return False
            return True
    return False
