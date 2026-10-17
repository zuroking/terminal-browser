# TLS fixture certificates

Regenerate from the repository root with:

```text
python tests/generate_certs.py
```

The fixture CA, valid localhost leaf, untrusted self-signed leaf, and
hostname-mismatch leaf expire on 2036-09-24. The expired localhost leaf expired
on 2021-09-24. The non-expired certificates have a validity window longer than
ten years from the initial generation date and must be regenerated before their
expiry date.
