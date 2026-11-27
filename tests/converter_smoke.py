#!/usr/bin/env python3
"""Exercise the HTTP contracts with fake inputs in containers without egress."""
import argparse
import base64
from contextlib import contextmanager
import subprocess
import time
from urllib.parse import urlencode, urlsplit, parse_qs
import uuid

REFERENCE = "ghcr.io/aethersailor/subconverter-extended@sha256:d90379f5a488dff06db29f9d3a63eb3a30ae632b26d73f2ce740aa122847f359"
KEY = "dwrjY6KiAMPxKdlF7T4AWFXXBtsxeHCXtBQYeCOdZV4"
UID = "2cae91b3-f85c-433b-88ee-a002b9ed6d61"
HY2 = "hysteria2://fixture-pass@example.invalid:443?sni=example.invalid#fixture-hy2"
REALITY = (
    f"vless://{UID}@203.0.113.9:443?security=reality&type=tcp"
    f"&sni=example.invalid&pbk={KEY}&sid=0123456789abcdef&fp=chrome"
    "&flow=xtls-rprx-vision#fixture-reality"
)
XHTTP = (
    f"vless://{UID}@example.invalid:443?security=tls&type=xhttp"
    "&mode=stream-one&path=%2Ffixture&host=example.invalid#fixture-xhttp"
)
YAML = f"""proxies:
  - name: native-stash
    type: vless
    server: 203.0.113.9
    port: 443
    uuid: {UID}
    tls: true
    sni: example.invalid
    reality-opts:
      public-key: {KEY}
      short-id: '0123456789abcdef'
      support-x25519mlkem768: true
  - name: native-xhttp
    type: vless
    server: example.invalid
    port: 443
    uuid: {UID}
    tls: true
    network: xhttp
    xhttp-opts:
      mode: stream-up
      path: /fixture
      x-padding-bytes: '100-1000'
      session-placement: header
      reuse-settings:
        max-concurrency: '8-32'
        h-keep-alive-period: 60
  - name: native-hy2
    type: hysteria2
    server: example.invalid
    port: 443
    auth: fixture-pass
    sni: example.invalid
"""
CONF = """[custom]
enable_rule_generator=true
overwrite_original_rules=true
custom_proxy_group=Fixture`select`.*`[]DIRECT
ruleset=Fixture,[]DOMAIN-SUFFIX,example.invalid
ruleset=DIRECT,[]FINAL
"""


def docker(*args, **kwargs):
    return subprocess.run(["docker", *args], check=True, capture_output=True, **kwargs).stdout


@contextmanager
def converter(image):
    name = f"omnisub-smoke-{uuid.uuid4().hex[:12]}"
    docker("run", "-d", "--rm", "--network", "none", "--name", name, image)
    try:
        for _ in range(40):
            try:
                if docker("exec", name, "wget", "-T", "2", "-qO-",
                          "http://127.0.0.1:25500/healthz").strip() == b"ok":
                    break
            except subprocess.CalledProcessError:
                pass
            time.sleep(0.25)
        else:
            raise AssertionError("converter health check never became ready")
        for file, contents in (("omnisub-fixture.ini", CONF), ("omnisub-fixture.yaml", YAML)):
            docker("exec", "-i", name, "sh", "-c", f"cat > /base/base/{file}",
                   input=contents.encode())
        yield name
    finally:
        docker("stop", name)


def request(name, target, url=HY2, **opts):
    query = urlencode(dict(target=target, url=url, config="base/omnisub-fixture.ini", **opts))
    try:
        return docker("exec", name, "wget", "-T", "5", "-qO-",
                      f"http://127.0.0.1:25500/sub?{query}")
    except subprocess.CalledProcessError as error:
        raise AssertionError(f"HTTP conversion failed for {target}: {opts}") from error


def baseline(name):
    outputs = {}
    for target in ("clash", "clashr"):
        for options in ({}, {"list": "true"}, {"expand": "true"}):
            output = request(name, target, **options)
            assert b"password: fixture-pass" in output and b"auth: fixture-pass" not in output
            outputs[(target, tuple(options.items()))] = output
    remote = request(name, "clash", "provider:FixtureProvider,interval:21600,https://example.com/proxies.yaml")
    assert b"proxy-providers:" in remote and b"FixtureProvider:" in remote
    outputs["clash-provider"] = remote
    outputs["surge-legacy"] = request(name, "surge", f"{HY2}|{REALITY}", list="true", ver="5")
    assert b"fixture-reality" not in outputs["surge-legacy"]
    outputs["shadowrocket"] = request(name, "shadowrocket")
    link = urlsplit(base64.b64decode(outputs["shadowrocket"]).decode().strip())
    assert link.username == "fixture-pass" and parse_qs(link.query)["sni"] == ["example.invalid"]
    stash = request(name, "stash")
    assert b"auth: fixture-pass" in stash and b"password: fixture-pass" not in stash
    return outputs


def candidate(name):
    modern = request(name, "surge", f"{HY2}|{REALITY}|{XHTTP}", list="true", ver="6")
    for token in (b"password=fixture-pass", f"username={UID}".encode(),
                  f"reality-public-key={KEY}".encode(), b"reality-short-id=0123456789abcdef",
                  b"flow=xtls-rprx-vision", b"xhttp-mode=stream-one", b"xhttp-path=/fixture"):
        assert token in modern, f"Surge 6 missing {token!r}"
    malformed = REALITY.replace("sid=0123456789abcdef", "sid=zz").replace("fixture-reality", "invalid")
    modern = request(name, "surge", f"{HY2}|{malformed}", list="true", ver="6")
    assert b"fixture-hy2" in modern and b"invalid =" not in modern
    stash = request(name, "stash", "base/omnisub-fixture.yaml")
    assert b"support-x25519mlkem768: true" in stash and b"auth: fixture-pass" in stash
    assert b"password: fixture-pass" not in stash
    for token in (b"x-padding-bytes: 100-1000", b"session-placement: header",
                  b"max-concurrency: 8-32", b"h-keep-alive-period: 60"):
        assert token in stash, f"Stash XHTTP missing {token!r}"
    assert b"xhttp-opts:" in request(name, "stash", XHTTP)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image")
    parser.add_argument("--reference", default=REFERENCE)
    parser.add_argument("--reference-only", action="store_true")
    args = parser.parse_args()
    with converter(args.reference if not args.reference_only else args.image) as ref:
        expected = baseline(ref)
    if not args.reference_only:
        with converter(args.image) as test:
            actual = baseline(test)
            for key in expected:
                assert actual[key] == expected[key], f"unexpected compatibility change: {key}"
            candidate(test)
    print("Conversion HTTP fixtures passed" if not args.reference_only else "Reference fixtures passed")


if __name__ == "__main__":
    main()
