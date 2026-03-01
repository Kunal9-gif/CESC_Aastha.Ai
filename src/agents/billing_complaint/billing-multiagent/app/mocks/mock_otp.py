def trigger_mock_otp(cid: str):
    """
    Simulates OTP sending.
    Does NOT verify.
    """
    print(f"\n[MOCK OTP SERVICE] OTP sent to registered mobile for CID: {cid}")
    return {"status": "OTP_SENT"}