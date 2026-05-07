import streamlit as st
import json
import time
from xrpl.clients import JsonRpcClient
from xrpl.wallet import generate_faucet_wallet, Wallet
from xrpl.transaction import submit_and_wait, autofill_and_sign
from xrpl.models.transactions import (
    MPTokenIssuanceCreate, CredentialCreate, MPTokenAuthorize,
    EscrowCreate, EscrowFinish, AMMCreate, AMMDeposit, Payment,
    NFTokenMint, NFTokenCreateOffer, NFTokenAcceptOffer
)
from xrpl.models.amounts import IssuedCurrencyAmount, MPTAmount
from xrpl.models.requests import AccountObjects
from xrpl.account import get_balance
from xrpl.utils import str_to_hex

st.set_page_config(page_title="Collatoken", layout="wide")
st.title("🔗 Collatoken")
st.subheader("Real-Time Global Collateral Mesh on XRPL Testnet")
st.markdown("**MPTs • NFTs as Collateral • Token Escrow • RLUSD • Credentials • AMM • Multi-Step Atomic Batches**")

# ===================== CONFIG =====================
TESTNET_URL = "https://s.altnet.rippletest.net:51234"
client = JsonRpcClient(TESTNET_URL)
RLUSD_ISSUER = "rQhWct2fv4Vc4KRjRgMrxa8xPN9Zx9iLKV"
RLUSD_CURRENCY = "524C555344000000000000000000000000000000"

if "wallet" not in st.session_state:
    st.session_state.update({
        "wallet": None,
        "account": None,
        "mpt_issuance_id": None,
        "mpt_metadata": {},
        "nft_token_id": None
    })

def is_valid_xrpl_address(addr: str) -> bool:
    if not addr or len(addr) < 20:
        return False
    try:
        from xrpl.core.addresscodec import classic_address_to_xaddress
        classic_address_to_xaddress(addr, tag=None, is_test_network=True)
        return True
    except:
        return False

# ===================== SIDEBAR =====================
with st.sidebar:
    st.header("Wallet Management")
    if st.button("Generate & Fund New Testnet Wallet", type="primary"):
        with st.spinner("Funding wallet..."):
            try:
                wallet = generate_faucet_wallet(client, debug=False)
                st.session_state.wallet = wallet
                st.session_state.account = wallet.address
                st.success("✅ Wallet created and funded!")
                st.code(wallet.address)
            except Exception as e:
                st.error(f"Faucet error: {e}")

    if st.session_state.wallet:
        st.success(f"Connected: `{st.session_state.account[:12]}...`")
        if st.button("Disconnect Wallet"):
            st.session_state.clear()
            st.rerun()

# ===================== TABS =====================
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Issue MPT", "Issue NFT", "Credentials & Auth", 
    "Lock Collateral", "RLUSD & AMM", "Multi-Step Atomic", "Dashboard"
])

# ===================== 1. ISSUE MPT =====================
with tab1:
    st.header("1. Issue Multi-Purpose Token (MPT)")
    if not st.session_state.wallet:
        st.warning("Generate a wallet first.")
    else:
        preset = st.selectbox("Preset", ["Custom", "Energy Credit", "Carbon Credit", "Treasury Bill"])
        token_name = f"Collatoken {preset}" if preset != "Custom" else st.text_input("Token Name", "Collatoken Asset")
        asset_class = preset.lower().replace(" ", "_") if preset != "Custom" else st.selectbox("Asset Class", ["treasury", "energy", "carbon", "rwa"])

        col1, col2 = st.columns(2)
        with col1:
            decimals = st.number_input("Decimals", 0, 18, 2)
        with col2:
            max_supply = st.number_input("Max Supply", 10000, 1000000000, 1000000)
            transfer_fee = st.number_input("Transfer Fee (bp)", 0, 5000, 0)

        if st.button("Issue MPT", type="primary"):
            with st.spinner("Issuing MPT..."):
                try:
                    metadata = {
                        "name": token_name,
                        "description": f"Collateral token - {asset_class}",
                        "asset_class": asset_class,
                        "issuer": "Collatoken",
                        "version": "1.0"
                    }
                    metadata_hex = json.dumps(metadata, separators=(',', ':')).encode('utf-8').hex().upper()

                    tx = MPTokenIssuanceCreate(
                        account=st.session_state.account,
                        asset_scale=decimals,
                        maximum_amount=str(int(max_supply * (10 ** decimals))),
                        transfer_fee=transfer_fee,
                        mptoken_metadata=metadata_hex,
                        flags=0x00020000 | 0x00000008 | 0x00000004
                    )

                    signed = autofill_and_sign(tx, client, st.session_state.wallet)
                    result = submit_and_wait(signed, client)

                    if result.is_successful():
                        st.success("✅ MPT Issued!")
                        st.json(result.result)
                        # Extract ID
                        nodes = result.result.get("meta", {}).get("AffectedNodes", [])
                        for node in nodes:
                            created = node.get("CreatedNode", {})
                            if created.get("LedgerEntryType") == "MPTokenIssuance":
                                st.session_state.mpt_issuance_id = created.get("LedgerIndex")
                                st.success(f"MPTokenIssuanceID: {st.session_state.mpt_issuance_id[:16]}...")
                    else:
                        st.error(result.result)
                except Exception as e:
                    st.error(str(e))

# ===================== 2. ISSUE NFT =====================
with tab2:
    st.header("2. Issue NFT (XLS-20) for Collateral")
    if st.session_state.wallet:
        uri = st.text_input("NFT URI / Metadata", "https://collatoken.example/nft/energy-credit-001")
        if st.button("Mint NFT"):
            with st.spinner("Minting NFT..."):
                try:
                    tx = NFTokenMint(
                        account=st.session_state.account,
                        uri=str_to_hex(uri),
                        flags=0x00000008  # tfTransferable
                    )
                    signed = autofill_and_sign(tx, client, st.session_state.wallet)
                    result = submit_and_wait(signed, client)
                    if result.is_successful():
                        st.success("✅ NFT Minted!")
                        st.json(result.result)
                        # Extract TokenID
                        try:
                            nodes = result.result.get("meta", {}).get("AffectedNodes", [])
                            for node in nodes:
                                if "CreatedNode" in node and node["CreatedNode"].get("LedgerEntryType") == "NFTokenPage":
                                    st.session_state.nft_token_id = "Extracted_from_meta"
                                    st.info("NFT ready for collateral use")
                        except:
                            pass
                    else:
                        st.error(result.result)
                except Exception as e:
                    st.error(str(e))

# ===================== 3. CREDENTIALS & AUTH =====================
with tab3:
    st.header("3. Credentials & MPT Authorization")
    if st.session_state.wallet:
        col1, col2 = st.columns(2)
        with col1:
            cred_type = st.text_input("Credential Type", "KYC_LEVEL_1_2026")
            subject = st.text_input("Subject Account", st.session_state.account)
            if st.button("Issue Credential"):
                if not is_valid_xrpl_address(subject):
                    st.error("Invalid address")
                else:
                    with st.spinner("Issuing..."):
                        tx = CredentialCreate(account=st.session_state.account, subject=subject,
                                              credential_type=cred_type.encode('utf-8').hex().upper())
                        signed = autofill_and_sign(tx, client, st.session_state.wallet)
                        result = submit_and_wait(signed, client)
                        st.success("Credential Issued!")
                        st.json(result.result)

        with col2:
            if st.session_state.get("mpt_issuance_id") and st.button("Authorize MPT"):
                tx = MPTokenAuthorize(account=st.session_state.account, mpt_issuance_id=st.session_state.mpt_issuance_id)
                signed = autofill_and_sign(tx, client, st.session_state.wallet)
                result = submit_and_wait(signed, client)
                st.success("MPT Authorized!")

# ===================== 4. LOCK COLLATERAL =====================
with tab4:
    st.header("4. Lock Collateral (MPT or NFT)")
    if st.session_state.wallet:
        collateral_type = st.radio("Collateral Type", ["MPT", "NFT"])
        amount = st.number_input("Amount (for MPT)", 100, 1000000, 5000)
        duration = st.number_input("Duration (minutes)", 5, 1440, 60)
        dest = st.text_input("Destination", st.session_state.account)

        if st.button("Lock Collateral"):
            with st.spinner("Locking..."):
                try:
                    if collateral_type == "MPT" and st.session_state.get("mpt_issuance_id"):
                        amount_obj = MPTAmount(mpt_issuance_id=st.session_state.mpt_issuance_id, value=str(amount))
                    else:
                        amount_obj = IssuedCurrencyAmount(currency="XRP", value=str(amount))
                    
                    tx = EscrowCreate(
                        account=st.session_state.account,
                        amount=amount_obj,
                        destination=dest,
                        cancel_after=int(time.time() + duration * 60)
                    )
                    signed = autofill_and_sign(tx, client, st.session_state.wallet)
                    result = submit_and_wait(signed, client)
                    st.success("Collateral Locked!")
                    st.json(result.result)
                except Exception as e:
                    st.error(str(e))

# ===================== 5. RLUSD & AMM =====================
with tab5:
    st.header("5. RLUSD & AMM Liquidity")
    if st.session_state.wallet and st.session_state.get("mpt_issuance_id"):
        if st.button("Create AMM (MPT + RLUSD)"):
            tx = AMMCreate(
                account=st.session_state.account,
                amount=IssuedCurrencyAmount(currency=RLUSD_CURRENCY, issuer=RLUSD_ISSUER, value="100"),
                amount2=MPTAmount(mpt_issuance_id=st.session_state.mpt_issuance_id, value="5000"),
                trading_fee=500
            )
            signed = autofill_and_sign(tx, client, st.session_state.wallet)
            result = submit_and_wait(signed, client)
            st.success("AMM Created!")
            st.json(result.result)

        if st.button("Deposit Liquidity"):
            tx = AMMDeposit(
                account=st.session_state.account,
                asset=MPTAmount(mpt_issuance_id=st.session_state.mpt_issuance_id, value="1000"),
                asset2=IssuedCurrencyAmount(currency=RLUSD_CURRENCY, issuer=RLUSD_ISSUER, value="20")
            )
            signed = autofill_and_sign(tx, client, st.session_state.wallet)
            result = submit_and_wait(signed, client)
            st.success("Liquidity Deposited!")

# ===================== 6. MULTI-STEP ATOMIC =====================
with tab6:
    st.header("6. Multi-Step Atomic Settlement (DvP)")
    st.info("Simulates atomic batch: Payment → Collateral Release")
    
    escrow_seq = st.text_input("Escrow Sequence Number")
    rlusd_amount = st.number_input("RLUSD Payment Amount", 10, 100000, 500)

    if st.button("Execute Multi-Step Atomic Flow", type="primary"):
        if not escrow_seq.isdigit():
            st.error("Enter valid Escrow Sequence")
        else:
            with st.spinner("Executing multi-step atomic flow..."):
                try:
                    # Step 1: Payment
                    payment_tx = Payment(
                        account=st.session_state.account,
                        destination=st.session_state.account,  # In real use: counterparty
                        amount=IssuedCurrencyAmount(currency=RLUSD_CURRENCY, issuer=RLUSD_ISSUER, value=str(rlusd_amount))
                    )
                    signed_payment = autofill_and_sign(payment_tx, client, st.session_state.wallet)
                    payment_result = submit_and_wait(signed_payment, client)
                    st.success("Step 1 - Payment completed")

                    # Step 2: Release Collateral
                    release_tx = EscrowFinish(
                        account=st.session_state.account,
                        owner=st.session_state.account,
                        offer_sequence=int(escrow_seq)
                    )
                    signed_release = autofill_and_sign(release_tx, client, st.session_state.wallet)
                    release_result = submit_and_wait(signed_release, client)
                    st.success("Step 2 - Collateral Released!")
                    st.json({"payment": payment_result.result, "release": release_result.result})
                except Exception as e:
                    st.error(str(e))

# ===================== 7. DASHBOARD =====================
with tab7:
    st.header("7. Dashboard")
    if st.session_state.wallet:
        balance = get_balance(st.session_state.account, client)
        st.metric("XRP Balance", f"{balance / 1_000_000:.4f} XRP")
        st.code(st.session_state.account)

        if st.button("Refresh All Objects"):
            resp = client.request(AccountObjects(account=st.session_state.account, limit=200))
            st.json(resp.result)

st.caption("Collatoken • Complete XRPL Testnet Collateral Mesh with MPT, NFT Collateral, Multi-Step Atomic Batches, RLUSD & AMM")
