# Signed CEP candidate provenance

The release was built with Adobe CEP Resources ZXPSignCmd 4.1.3 x64 from:
https://github.com/Adobe-CEP/CEP-Resources/blob/master/ZXPSignCMD/4.1.3/x64/ZXPSignCmd.exe

Downloaded executable Git blob SHA-1 was checked against Adobe GitHub metadata:
`f5df2ed805e04a4d3c6adc722f602d4df6c762f7`.
The executable SHA-256 used for this build is recorded in release.json.
Adobe's verifier returned `Signature verified successfully` for the generated ZXP.

The candidate uses a self-signed popo-studio certificate with 3650-day validity,
created 2026-10-21, without an external timestamp. Certificate expiry therefore
applies. The signature and public certificate are in META-INF/signatures.xml;
private key and password are stored only outside the package in ignored local
build state. They are not required to install or run this extension. Keep the
signing credential securely backed up for later releases; never commit it.

A successful signature check validates package integrity. It does not prove
Premiere 26 native panel loading or operation correctness; host acceptance is
pending installation of a supported version.
