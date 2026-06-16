import json
import os

import pytest

from core.parser import VlessConfig
from core.xray import generate_xray_config, write_xray_config


def _config(**kwargs) -> VlessConfig:
    defaults = dict(
        uuid="9d507afd-7e90-4b7e-8bd8-6877f7a304ae",
        host="1.2.3.4",
        port=443,
        raw_uri="vless://...",
        name="Test",
        security="none",
        type="tcp",
        flow="",
        header_type="none",
        sni="",
        fp="",
        alpn="",
        pbk="",
        sid="",
        spx="",
        path="/",
        host_header="",
        service_name="",
    )
    defaults.update(kwargs)
    return VlessConfig(**defaults)


class TestGenerateXrayConfig:
    def test_basic_structure(self):
        cfg = _config()
        result = generate_xray_config(cfg, local_port=10800)

        assert result["log"]["loglevel"] == "warning"
        assert len(result["inbounds"]) == 1
        assert len(result["outbounds"]) == 1

        inbound = result["inbounds"][0]
        assert inbound["port"] == 10800
        assert inbound["protocol"] == "socks"
        assert inbound["settings"]["udp"] is True

    def test_outbound_vless_fields(self):
        cfg = _config(flow="xtls-rprx-vision", security="reality", sni="example.com", pbk="key", sid="sid1")
        result = generate_xray_config(cfg, local_port=10800)

        vnext = result["outbounds"][0]["settings"]["vnext"][0]
        assert vnext["address"] == "1.2.3.4"
        assert vnext["port"] == 443
        user = vnext["users"][0]
        assert user["id"] == cfg.uuid
        assert user["encryption"] == "none"
        assert user["flow"] == "xtls-rprx-vision"

    def test_empty_flow_not_in_user(self):
        cfg = _config(flow="")
        result = generate_xray_config(cfg, local_port=10800)
        user = result["outbounds"][0]["settings"]["vnext"][0]["users"][0]
        assert "flow" not in user

    def test_tcp_reality_stream(self):
        cfg = _config(
            security="reality", sni="cdn.example.com", fp="firefox",
            pbk="pubkey123", sid="shortid", spx="/spider",
        )
        stream = generate_xray_config(cfg, 10800)["outbounds"][0]["streamSettings"]
        assert stream["network"] == "tcp"
        assert stream["security"] == "reality"
        rs = stream["realitySettings"]
        assert rs["serverName"] == "cdn.example.com"
        assert rs["fingerprint"] == "firefox"
        assert rs["publicKey"] == "pubkey123"
        assert rs["shortId"] == "shortid"
        assert rs["spiderX"] == "/spider"

    def test_tcp_tls_stream(self):
        cfg = _config(security="tls", sni="example.com", fp="chrome", alpn="h2,http/1.1")
        stream = generate_xray_config(cfg, 10800)["outbounds"][0]["streamSettings"]
        assert stream["network"] == "tcp"
        assert stream["security"] == "tls"
        tls = stream["tlsSettings"]
        assert tls["serverName"] == "example.com"
        assert tls["alpn"] == ["h2", "http/1.1"]

    def test_tcp_tls_no_alpn(self):
        cfg = _config(security="tls", sni="example.com", alpn="")
        stream = generate_xray_config(cfg, 10800)["outbounds"][0]["streamSettings"]
        assert "alpn" not in stream["tlsSettings"]

    def test_tcp_plain_stream(self):
        cfg = _config(security="none", header_type="http")
        stream = generate_xray_config(cfg, 10800)["outbounds"][0]["streamSettings"]
        assert stream["network"] == "tcp"
        assert "security" not in stream
        assert stream["tcpSettings"]["header"]["type"] == "http"

    def test_ws_stream(self):
        cfg = _config(type="ws", security="tls", sni="ws.example.com", path="/ws", host_header="ws.example.com")
        stream = generate_xray_config(cfg, 10800)["outbounds"][0]["streamSettings"]
        assert stream["network"] == "ws"
        assert stream["wsSettings"]["path"] == "/ws"
        assert stream["wsSettings"]["headers"]["Host"] == "ws.example.com"
        assert "tlsSettings" in stream

    def test_ws_no_host_header(self):
        cfg = _config(type="ws", host_header="")
        stream = generate_xray_config(cfg, 10800)["outbounds"][0]["streamSettings"]
        assert stream["wsSettings"]["headers"] == {}

    def test_grpc_stream(self):
        cfg = _config(type="grpc", security="tls", sni="grpc.example.com", service_name="myService")
        stream = generate_xray_config(cfg, 10800)["outbounds"][0]["streamSettings"]
        assert stream["network"] == "grpc"
        assert stream["grpcSettings"]["serviceName"] == "myService"
        assert "tlsSettings" in stream

    def test_local_port_in_inbound(self):
        cfg = _config()
        for port in (10800, 10815, 10820):
            result = generate_xray_config(cfg, port)
            assert result["inbounds"][0]["port"] == port


class TestWriteXrayConfig:
    def test_creates_file(self, tmp_path):
        cfg = _config()
        path = write_xray_config(cfg, local_port=10800, config_dir=str(tmp_path))
        assert os.path.exists(path)
        assert path.endswith("proxy_10800.json")

    def test_creates_dir_if_missing(self, tmp_path):
        cfg = _config()
        target = str(tmp_path / "nested" / "dir")
        path = write_xray_config(cfg, local_port=10801, config_dir=target)
        assert os.path.exists(path)

    def test_file_is_valid_json(self, tmp_path):
        cfg = _config(security="reality", sni="x.com", pbk="k", sid="s")
        path = write_xray_config(cfg, local_port=10800, config_dir=str(tmp_path))
        with open(path) as f:
            data = json.load(f)
        assert data["inbounds"][0]["port"] == 10800
