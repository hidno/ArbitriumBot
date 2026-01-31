# generate_wallet.py
from eth_account import Account
import secrets

# Generate random private key
private_key = "0x" + secrets.token_hex(32)

# Create account from private key
account = Account.from_key(private_key)

print("=" * 60)
print("YOUR NEW ETHEREUM WALLET")
print("=" * 60)
print(f"Private Key: {private_key}")
print(f"Public Address: {account.address}")
print("=" * 60)
print("\n CRITICAL SECURITY WARNINGS:")
print("1. NEVER share your private key with anyone")
print("2. Save private key in password manager (LastPass/1Password)")
print("3. Write private key on paper, store in safe")
print("4. Losing private key = losing all funds FOREVER")
print("=" * 60)
