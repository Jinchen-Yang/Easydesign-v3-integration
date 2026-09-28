from email.message import Message

import pytest

from easydesign.product.contracts import ProductError
from easydesign.product.transport_policy import TransportPolicy


def headers(*values: str) -> Message:
    message = Message()
    for value in values:
        message["X-Real-IP"] = value
    return message


def test_forwarded_identity_requires_explicitly_trusted_immediate_proxy():
    supplied = headers("198.51.100.24")
    assert TransportPolicy().client_ip("127.0.0.1", supplied) == "127.0.0.1"
    policy = TransportPolicy(trusted_proxies=("127.0.0.1/32",))
    assert policy.client_ip("127.0.0.1", supplied) == "198.51.100.24"
    assert policy.client_ip("192.0.2.2", supplied) == "192.0.2.2"
    assert policy.client_ip("127.0.0.1", headers()) == "127.0.0.1"


@pytest.mark.parametrize(
    "values",
    [
        ("198.51.100.24, 10.0.0.1",),
        ("bad-address",),
        ("127.0.0.1:9000",),
        ("fe80::1%eth0",),
        ("",),
        ("198.51.100.24", "198.51.100.25"),
    ],
)
def test_trusted_proxy_header_is_one_unambiguous_ip_not_a_chain(values):
    policy = TransportPolicy(trusted_proxies=("127.0.0.1/32",))
    with pytest.raises(ProductError) as error:
        policy.client_ip("127.0.0.1", headers(*values))
    assert error.value.code == "invalid_client_ip"
