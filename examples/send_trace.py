#!/usr/bin/env python3
"""Send explicit synthetic OTLP fixtures. Does not populate any dashboard automatically.

NEURALOPS_INGESTION_KEY must be provided via environment/secret store.
Use --inject-timeout to exercise failure detection. No external model is called.
"""
import argparse
import json
import os
import secrets
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--endpoint', default='http://localhost:4318')
parser.add_argument('--count', type=int, default=1)
parser.add_argument('--inject-timeout', action='store_true')
args = parser.parse_args()
if not 1 <= args.count <= 100:
    parser.error('count must be 1–100')
parsed = urlparse(args.endpoint)
if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in {'localhost', '127.0.0.1'}):
    parser.error('Use HTTPS outside loopback development.')
secret = os.environ.get('NEURALOPS_INGESTION_KEY')
if not secret:
    parser.error('Set NEURALOPS_INGESTION_KEY via your secret store/environment. The sender never prints it.')
for _ in range(args.count):
    trace_id, root_id, child_id = secrets.token_hex(16), secrets.token_hex(8), secrets.token_hex(8)
    start = time.time_ns()
    child_start = time.time_ns()
    error = False
    try:
        time.sleep(.015)
        if args.inject_timeout:
            raise TimeoutError('Explicit synthetic fixture failure')
    except TimeoutError:
        error = True
    child_end, end = time.time_ns(), time.time_ns()
    attributes = [{'key': 'error.type', 'value': {'stringValue': 'SyntheticTimeoutError'}}] if error else []
    batch = {'resourceSpans': [{'resource': {'attributes': [{'key': 'service.name', 'value': {'stringValue': 'synthetic-fixture-rag'}}]},
                                'scopeSpans': [{'spans': [
                                    {'traceId': trace_id, 'spanId': root_id, 'name': 'synthetic-fixture/request',
                                     'startTimeUnixNano': str(start), 'endTimeUnixNano': str(end), 'status': {'code': 2 if error else 1}},
                                    {'traceId': trace_id, 'spanId': child_id, 'parentSpanId': root_id, 'name': 'synthetic-fixture/retrieval',
                                     'startTimeUnixNano': str(child_start), 'endTimeUnixNano': str(child_end), 'status': {'code': 2 if error else 1},
                                     'attributes': attributes}]}]}]}
    request = urllib.request.Request(args.endpoint.rstrip('/')+'/v1/traces', data=json.dumps(batch).encode(),
                                     headers={'Content-Type': 'application/json', 'Authorization': f'Bearer {secret}'}, method='POST')
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            print(f'Synthetic fixture accepted: {trace_id} ({response.status}); actual measured wall-clock {(end-start)/1e6:.2f} ms.')
    except urllib.error.HTTPError as error:
        print(f'Gateway rejected synthetic fixture: HTTP {error.code}. No credential was logged.')
        raise SystemExit(1) from None
