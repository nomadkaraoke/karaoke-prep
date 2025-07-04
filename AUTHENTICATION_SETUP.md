# Karaoke Generator Authentication Setup Guide

This guide explains how to set up and configure the authentication system for the Karaoke Generator web application.

## Overview

The authentication system supports four types of access:

1. **Admin Access** - Full system access with admin tools
2. **Unlimited Access** - Unlimited karaoke generation without admin tools  
3. **Limited Access** - Fixed number of uses (e.g., 1, 5, 10 uses)
4. **Stripe Access** - Payment-validated access tokens

## Initial Setup

### 1. Configure Admin Tokens

Admin tokens are set via environment variables in your Modal deployment:

```bash
# Set one or more admin tokens (comma-separated)
modal secret create env-vars ADMIN_TOKENS="admin-master-key-2024,backup-admin-token"

# Set an auth secret for session security (optional but recommended)
modal secret create env-vars AUTH_SECRET="your-random-secret-string-here"
```

### 2. Deploy the Updated Application

Deploy your updated `app.py` with the authentication system:

```bash
modal deploy app.py
```

### 3. Access the Admin Interface

1. Go to your frontend URL: `https://gen.nomadkaraoke.com`
2. Enter one of your admin tokens when prompted
3. Click the **Admin** panel in the top-right corner
4. Click **🎫 Manage Tokens** to create access codes

## Creating Access Tokens

### Admin Interface

Once logged in as an admin, you can create tokens through the web interface:

1. Open the **Token Management** modal
2. Fill in the token creation form:
   - **Type**: Choose the token type
   - **Token**: Enter the token string (e.g., `SUMMER2024`, `PROMO-10-USES`)
   - **Max Uses**: For limited tokens, specify the number of uses
   - **Description**: Optional description for tracking

### API Creation (Advanced)

You can also create tokens via the API:

```bash
# Create unlimited access token
curl -X POST "https://your-modal-url/api/admin/tokens/create" \
  -H "Authorization: Bearer your-admin-token" \
  -H "Content-Type: application/json" \
  -d '{
    "token_type": "unlimited",
    "token_value": "UNLIMITED-PROMO-2024",
    "description": "Marketing campaign unlimited access"
  }'

# Create limited access token
curl -X POST "https://your-modal-url/api/admin/tokens/create" \
  -H "Authorization: Bearer your-admin-token" \
  -H "Content-Type: application/json" \
  -d '{
    "token_type": "limited",
    "token_value": "TRIAL-5-USES",
    "max_uses": 5,
    "description": "5-use trial token"
  }'
```

## Token Examples

### Admin Tokens
```
admin-master-2024
nomad-admin-key
backup-admin-access
```

### Unlimited Promo Codes
```
UNLIMITED-BETA
NOMAD-VIP-2024
CREATOR-ACCESS
INFLUENCER-CODE
```

### Limited Use Codes
```
TRIAL-1-USE          (1 use)
DEMO-5-VIDEOS        (5 uses)
WORKSHOP-10-USES     (10 uses)
CONFERENCE-PACK      (20 uses)
```

### Stripe Payment Tokens
```
stripe_1234567890abcdef     (Generated automatically)
payment_verified_xyz123     (Generated after payment)
```

## Token Management

### Viewing Token Usage

Admin users can see detailed usage statistics:
- Total uses per token
- Number of jobs created
- Last used timestamp
- Active/revoked status

### Revoking Tokens

Revoke compromised or expired tokens:
1. Go to **Token Management**
2. Find the token in the list
3. Click **Revoke** button
4. Confirm the action

### Usage Tracking

The system automatically tracks:
- When tokens are used
- Which jobs were created with each token
- Remaining uses for limited tokens
- Usage patterns and statistics

## Security Considerations

### Admin Token Security

- Use strong, unique admin tokens
- Store admin tokens securely
- Rotate admin tokens periodically
- Limit the number of admin tokens

### Access Token Best Practices

- Use descriptive token names
- Include purpose in token description
- Set appropriate use limits
- Monitor token usage regularly
- Revoke unused or suspicious tokens

### Environment Variables

Required environment variables:
```bash
ADMIN_TOKENS="token1,token2,token3"  # Required
AUTH_SECRET="random-secret-string"   # Recommended
```

## Stripe Integration (Future Implementation)

*Note: This section documents the planned Stripe payment integration for future development.*

### Overview

The authentication system is already prepared for Stripe integration with:
- `stripe` token type implemented
- Payment tracking infrastructure in place
- Webhook endpoint structure ready
- Token expiration and usage limits supported

### Implementation Steps

#### 1. Stripe Account Setup
```bash
# Required Stripe configuration
modal secret create env-vars STRIPE_SECRET_KEY="sk_live_..."
modal secret create env-vars STRIPE_PUBLISHABLE_KEY="pk_live_..."
modal secret create env-vars STRIPE_WEBHOOK_SECRET="whsec_..."
```

#### 2. Payment Products Configuration

Create Stripe products for different access levels:
```python
# Example product configurations
STRIPE_PRODUCTS = {
    "single_video": {
        "price_id": "price_1234567890",
        "uses": 1,
        "name": "Single Video Generation"
    },
    "video_pack_5": {
        "price_id": "price_0987654321", 
        "uses": 5,
        "name": "5-Video Pack"
    },
    "monthly_unlimited": {
        "price_id": "price_monthly_unlimited",
        "uses": -1,  # unlimited
        "expires_days": 30,
        "name": "Monthly Unlimited Access"
    }
}
```

#### 3. Frontend Payment Flow

Add to frontend (`app.js`):
```javascript
// Payment button integration
async function initiateStripePayment(productType) {
    const response = await authenticatedFetch(`${API_BASE_URL}/stripe/create-checkout`, {
        method: 'POST',
        body: JSON.stringify({ 
            product_type: productType,
            success_url: window.location.origin + '/payment-success',
            cancel_url: window.location.origin + '/payment-cancelled'
        })
    });
    
    const { checkout_url } = await response.json();
    window.location.href = checkout_url;
}
```

#### 4. Backend Payment Endpoints

Add to `app.py`:
```python
import stripe

@api_app.post("/api/stripe/create-checkout")
async def create_stripe_checkout(request: PaymentRequest):
    """Create Stripe checkout session."""
    try:
        stripe.api_key = os.environ.get("STRIPE_SECRET_KEY")
        
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            line_items=[{
                'price': STRIPE_PRODUCTS[request.product_type]['price_id'],
                'quantity': 1,
            }],
            mode='payment',
            success_url=request.success_url + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=request.cancel_url,
            metadata={'product_type': request.product_type}
        )
        
        return {"checkout_url": session.url}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@api_app.post("/api/stripe/webhook")
async def stripe_webhook(request: Request):
    """Handle Stripe webhook events."""
    payload = await request.body()
    sig_header = request.headers.get('stripe-signature')
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, os.environ.get("STRIPE_WEBHOOK_SECRET")
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        await handle_successful_payment(session)
    
    return {"status": "success"}

async def handle_successful_payment(session):
    """Generate access token after successful payment."""
    product_type = session['metadata']['product_type']
    product_config = STRIPE_PRODUCTS[product_type]
    
    # Generate unique token
    payment_token = f"stripe_{session['id']}"
    
    # Create token in auth system
    token_data = {
        "type": "stripe",
        "max_uses": product_config['uses'],
        "description": f"Paid access: {product_config['name']}",
        "created_at": time.time(),
        "stripe_session_id": session['id'],
        "customer_email": session.get('customer_details', {}).get('email'),
        "active": True
    }
    
    # Add expiration for time-limited products
    if 'expires_days' in product_config:
        token_data["expires_at"] = time.time() + (product_config['expires_days'] * 24 * 60 * 60)
    
    # Store token
    stored_tokens = auth_tokens_dict.get("tokens", {})
    stored_tokens[payment_token] = token_data
    auth_tokens_dict["tokens"] = stored_tokens
    
    # TODO: Send email with access token to customer
    # send_access_token_email(session['customer_details']['email'], payment_token)
```

#### 5. Email Integration

For sending access tokens via email after payment:
```python
# Add email service (SendGrid, Mailgun, etc.)
async def send_access_token_email(email: str, token: str):
    """Send access token to customer via email."""
    subject = "Your Nomad Karaoke Access Token"
    body = f"""
    Thank you for your purchase!
    
    Your access token: {token}
    
    To use your karaoke generator:
    1. Go to https://gen.nomadkaraoke.com
    2. Enter your access token: {token}
    3. Start creating karaoke videos!
    
    Questions? Contact support@nomadkaraoke.com
    """
    # Send email implementation here
```

#### 6. Payment Success Page

Add payment success handling:
```javascript
// Handle successful payment redirect
async function handlePaymentSuccess() {
    const urlParams = new URLSearchParams(window.location.search);
    const sessionId = urlParams.get('session_id');
    
    if (sessionId) {
        // Show success message and instructions for token retrieval
        showSuccess('Payment successful! Check your email for your access token.');
        
        // Optional: Auto-retrieve token if customer is logged in
        try {
            const response = await fetch(`${API_BASE_URL}/stripe/get-token/${sessionId}`);
            if (response.ok) {
                const { token } = await response.json();
                await login(token);
            }
        } catch (error) {
            console.log('Auto-login failed, user will need to enter token manually');
        }
    }
}
```

#### 7. Testing Configuration

For testing with Stripe test keys:
```bash
# Test environment
modal secret create env-vars STRIPE_SECRET_KEY="sk_test_..."
modal secret create env-vars STRIPE_PUBLISHABLE_KEY="pk_test_..."
modal secret create env-vars STRIPE_WEBHOOK_SECRET="whsec_test_..."
```

#### 8. Security Considerations

- Validate all webhook signatures
- Store minimal payment data (just session IDs)
- Use HTTPS for all payment flows
- Implement rate limiting on payment endpoints
- Log all payment events for audit trail
- Never store credit card information

#### 9. Admin Monitoring

Add Stripe payment monitoring to admin panel:
```javascript
// Admin view of Stripe payments
async function showStripePayments() {
    const response = await authenticatedFetch(`${API_BASE_URL}/admin/stripe/payments`);
    const payments = await response.json();
    
    // Display payment history, refunds, token generation stats
}
```

### Testing Workflow

1. Set up Stripe test environment
2. Create test products and prices
3. Test checkout flow with test cards
4. Verify webhook delivery and token generation
5. Test email delivery
6. Validate token usage and limits

### Production Checklist

- [ ] Live Stripe keys configured
- [ ] Webhook endpoints registered with Stripe
- [ ] SSL certificates valid
- [ ] Email service configured
- [ ] Payment success/cancel pages deployed
- [ ] Admin monitoring dashboard ready
- [ ] Customer support process documented

This foundation allows for rapid Stripe integration when you're ready to monetize the service.

## Troubleshooting

### Common Issues

1. **Authentication Failed**
   - Check if token exists and is active
   - Verify token spelling and case
   - Ensure token hasn't been revoked

2. **Admin Access Denied**
   - Verify admin token is in ADMIN_TOKENS environment variable
   - Check Modal secrets are properly configured
   - Redeploy if environment variables were changed

3. **No Uses Remaining**
   - Check token usage in admin panel
   - Create new token or increase limits
   - Verify usage tracking is working correctly

### Debugging

Enable debug logging in the backend:
```python
logging.getLogger().setLevel(logging.DEBUG)
```

Check authentication status via API:
```bash
curl -X POST "https://your-modal-url/api/auth/validate" \
  -H "Authorization: Bearer your-token"
```

## Support

For issues with the authentication system:

1. Check the admin panel for token status
2. Review Modal logs for authentication errors  
3. Verify environment variables are set correctly
4. Contact system administrator if problems persist

## Example Deployment Workflow

1. **Development**: Use admin tokens for testing
2. **Staging**: Create test tokens for validation  
3. **Production**: 
   - Set strong admin tokens
   - Create marketing promo codes
   - Set up Stripe integration
   - Monitor usage and security

This authentication system provides flexible access control while maintaining security and usage tracking for your karaoke generation service. 