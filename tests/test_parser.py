import pytest

from core.parser import ParseResult, VlessConfig, parse_vless, parse_vless_list

VALID_REALITY_URI = (
    "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@155.117.137.168:443"
    "?flow=xtls-rprx-vision&type=tcp&headerType=none&security=reality"
    "&fp=firefox&sni=cdn3-87.yahoo.com"
    "&pbk=CMkW1axrhEXsamplekey"
    "&sid=7e77e7e2cf2b7a79"
    "#Amsterdam"
)


class TestParseVless:
    def test_valid_reality_uri(self):
        result = parse_vless(VALID_REALITY_URI)
        assert result.success is True
        assert result.config is not None
        c = result.config
        assert c.uuid == "9d507afd-7e90-4b7e-8bd8-6877f7a304ae"
        assert c.host == "155.117.137.168"
        assert c.port == 443
        assert c.security == "reality"
        assert c.flow == "xtls-rprx-vision"
        assert c.sni == "cdn3-87.yahoo.com"
        assert c.pbk == "CMkW1axrhEXsamplekey"
        assert c.sid == "7e77e7e2cf2b7a79"
        assert c.name == "Amsterdam"
        assert "#" not in c.raw_uri
        assert c.host in c.raw_uri

    def test_no_vless_prefix(self):
        result = parse_vless("https://example.com")
        assert result.success is False
        assert "vless://" in result.error

    def test_invalid_uuid(self):
        uri = "vless://not-a-uuid@1.2.3.4:443?security=none#test"
        result = parse_vless(uri)
        assert result.success is False
        assert "UUID" in result.error

    def test_port_zero(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:0"
            "?security=none"
        )
        result = parse_vless(uri)
        assert result.success is False
        assert "port" in result.error.lower()

    def test_port_too_large(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:99999"
            "?security=none"
        )
        result = parse_vless(uri)
        assert result.success is False
        assert "port" in result.error.lower()

    def test_reality_missing_pbk(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
            "?security=reality&sni=example.com"
        )
        result = parse_vless(uri)
        assert result.success is False
        assert "pbk" in result.error

    def test_reality_missing_sni(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
            "?security=reality&pbk=somekey"
        )
        result = parse_vless(uri)
        assert result.success is False
        assert "sni" in result.error

    def test_empty_string(self):
        result = parse_vless("")
        assert result.success is False

    def test_defaults(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@example.com:443"
            "?security=none"
        )
        result = parse_vless(uri)
        assert result.success is True
        c = result.config
        assert c.type == "tcp"
        assert c.header_type == "none"
        assert c.path == "/"
        assert c.name == ""

    def test_fragment_url_decoded(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@example.com:443"
            "?security=none#My%20Server"
        )
        result = parse_vless(uri)
        assert result.success is True
        assert result.config.name == "My Server"

    def test_ws_path_must_start_with_slash(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@example.com:443"
            "?security=none&type=ws&path=noslash"
        )
        result = parse_vless(uri)
        assert result.success is False
        assert "path" in result.error.lower()

    def test_flow_xtls_requires_reality_or_tls(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae@1.2.3.4:443"
            "?security=none&flow=xtls-rprx-vision"
        )
        result = parse_vless(uri)
        assert result.success is False
        assert "flow" in result.error.lower()

    def test_ipv6_host(self):
        uri = (
            "vless://9d507afd-7e90-4b7e-8bd8-6877f7a304ae"
            "@[2001:db8::1]:443?security=none"
        )
        result = parse_vless(uri)
        assert result.success is True
        assert result.config.host == "2001:db8::1"


class TestParseVlessList:
    def _make_uri(self, uuid_suffix: str, host: str, port: int = 443) -> str:
        base_uuid = f"9d507afd-7e90-4b7e-8bd8-{uuid_suffix}"
        return (
            f"vless://{base_uuid}@{host}:{port}"
            "?security=reality&sni=example.com&pbk=key123"
        )

    def test_mixed_valid_and_invalid(self):
        text = "\n".join([
            self._make_uri("6877f7a304ae", "1.1.1.1"),
            "vless://not-valid",
            self._make_uri("6877f7a304ab", "2.2.2.2"),
        ])
        configs, results = parse_vless_list(text)
        assert len(configs) == 2
        assert len(results) == 3
        assert results[1].success is False

    def test_deduplication(self):
        uri = self._make_uri("6877f7a304ae", "1.1.1.1")
        text = f"{uri}\n{uri}\n{uri}"
        configs, results = parse_vless_list(text)
        assert len(configs) == 1
        assert len(results) == 3

    def test_skips_non_vless_lines(self):
        text = "# comment\nhttps://example.com\n" + self._make_uri("6877f7a304ae", "1.1.1.1")
        configs, results = parse_vless_list(text)
        assert len(configs) == 1
        assert len(results) == 1

    def test_empty_input(self):
        configs, results = parse_vless_list("")
        assert configs == []
        assert results == []
