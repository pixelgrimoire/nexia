"""Cross-platform E2E smoke test for local stack.
- Posts a sample webhook into webhook-receiver (in-container HTTP call)
- Checks Redis stream `nf:sent` before and after via docker compose exec

Usage:
  python scripts/e2e_test.py

Exits 0 on success (nf:sent increased), non-zero otherwise.
"""
import subprocess
import sys
import base64

def run(cmd):
    # run command, return (returncode, stdout)
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def xlen_nf_sent():
    rc, out, err = run(["docker","compose","exec","-T","redis","redis-cli","XLEN","nf:sent"])
    if rc != 0:
        print("Error running redis XLEN:", err)
        return None
    try:
        return int(out.strip())
    except Exception:
        print("Unexpected XLEN output:", out)
        return None


def xrevrange_last_entry():
    # returns (id, dict) or (None, None)
    rc, out, err = run(["docker","compose","exec","-T","redis","redis-cli","--raw","XREVRANGE","nf:sent","+","-","COUNT","1"])
    if rc != 0:
        print("Error running redis XREVRANGE:", err)
        return None, None
    if not out:
        return None, None
    # redis-cli --raw prints id on first line, then alternating key/value lines
    lines = out.splitlines()
    entry_id = lines[0].strip()
    fields = {}
    pairs = lines[1:]
    for i in range(0, len(pairs), 2):
        k = pairs[i].strip()
        v = pairs[i+1].strip() if i+1 < len(pairs) else ""
        fields[k] = v
    return entry_id, fields

# base64 payload to avoid shell quoting issues
b64 = 'eyJlbnRyeSI6IFt7ImNoYW5nZXMiOiBbeyJ2YWx1ZSI6IHsibWVzc2FnZXMiOiBbeyJmcm9tIjogIjk4NzYiLCAidGV4dCI6IHsiYm9keSI6ICJQSVBFX0VOVEVSX1RFU1QifX1dfX1dfV0sICJjb250YWN0IjogeyJwaG9uZSI6ICI5ODc2In19'

def main():
    print("Counting nf:sent (before) ...")
    before = xlen_nf_sent()
    if before is None:
        sys.exit(2)
    print("nf:sent before:", before)

    # Build python code to run inside the webhook-receiver container
    inner = (
        "import http.client,base64,hmac,hashlib\n"
        f"b64='{b64}'\n"
        "body=base64.b64decode(b64)\n"
        "secret=b'dev_secret'\n"
        "sig='sha256='+hmac.new(secret, body, hashlib.sha256).hexdigest()\n"
        "conn=http.client.HTTPConnection('127.0.0.1',8000)\n"
        "conn.request('POST','/api/webhooks/whatsapp',body,{'X-Hub-Signature-256':sig,'Content-Type':'application/json'})\n"
        "r=conn.getresponse()\n"
        "print(r.status)\n"
        "print(r.read().decode())\n"
    )

    print("Posting test webhook into webhook-receiver (in-container) ...")
    rc, out, err = run(["docker","compose","exec","-T","webhook-receiver","python","-c", inner])
    print(out)
    if rc != 0:
        print("Error posting webhook:", err)
        sys.exit(3)

    # small delay to allow workers to process
    import time
    time.sleep(1)

    print("Counting nf:sent (after) ...")
    after = xlen_nf_sent()
    if after is None:
        sys.exit(4)
    print("nf:sent after:", after)

    if after > before:
        # verify content of last entry contains test marker
        eid, fields = xrevrange_last_entry()
        print("last nf:sent id:", eid)
        print(fields)
        text = fields.get('text') or fields.get('message') or ''
        orig = fields.get('orig_text') or ''
        if 'ENTER_TEST' in text or 'ENTER_TEST' in orig:
            print(f"E2E PASS: nf:sent increased ({before} -> {after}) and entry contains test marker")
            sys.exit(0)
        else:
            print(f"E2E FAIL: nf:sent increased but entry did not contain test marker ({before} -> {after})")
            sys.exit(6)
    else:
        print(f"E2E FAIL: nf:sent did not increase ({before} -> {after})")
        sys.exit(5)


if __name__ == "__main__":
    main()
