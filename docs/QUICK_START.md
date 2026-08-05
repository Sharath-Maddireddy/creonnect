# Advanced Analysis - Quick Start Guide

## Overview

The Advanced Account Analysis system provides three new features:

1. **Revenue Calculator** - Get rate recommendations for brand deals
2. **Risk Assessment** - Monitor for engagement and brand safety issues
3. **Brand Readiness** - Detailed scoring for brand partnership readiness

---

## Quick Start

### 1. Revenue Calculator

Get a rate recommendation for your creator account:

```bash
curl -X POST http://localhost:8000/api/account-analysis/revenue \
  -H "Content-Type: application/json" \
  -d '{
    "engagement_rate": 0.05,
    "follower_count": 50000,
    "niche": "fashion"
  }'
```

**Response:**
```json
{
  "recommended_rate": 810.75,
  "rate_min": 648.6,
  "rate_max": 972.9,
  "optimization_tips": [...]
}
```

### 2. Risk Assessment

Check for risks in your account:

```bash
curl -X POST http://localhost:8000/api/account-analysis/risks \
  -H "Content-Type: application/json" \
  -d '{"posts": [...]}'
```

**Response:**
```json
{
  "overall_risk_level": "low",
  "risks": [],
  "risk_count": 0
}
```

### 3. Brand Readiness

Get your brand readiness score:

```bash
curl -X POST http://localhost:8000/api/account-analysis/brand-readiness \
  -H "Content-Type: application/json" \
  -d '{"posts": [...]}'
```

**Response:**
```json
{
  "overall_score": 73.8,
  "overall_label": "Marketable",
  "improvement_opportunities": ["Content Quality", "Niche Clarity"]
}
```

---

## Python Example

```python
import requests

# Calculate rate recommendation
response = requests.post(
    'http://localhost:8000/api/account-analysis/revenue',
    json={
        'engagement_rate': 0.05,
        'follower_count': 50000,
        'niche': 'fashion',
        'brand_safety_score': 90,
        'content_quality_score': 80
    }
)

data = response.json()
print(f"Recommended rate: ${data['recommended_rate']:.2f}")
print(f"Rate range: ${data['rate_min']:.2f} - ${data['rate_max']:.2f}")
print(f"\nOptimization tips:")
for tip in data['optimization_tips']:
    print(f"  • {tip}")
```

---

## JavaScript Example

```javascript
// Fetch rate recommendation
const response = await fetch('/api/account-analysis/revenue', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    engagement_rate: 0.05,
    follower_count: 50000,
    niche: 'fashion'
  })
});

const data = await response.json();
console.log(`Recommended rate: $${data.recommended_rate}`);
```

---

## Integration with Dashboard

To add these features to your dashboard:

```jsx
import AdvancedAnalysis from './components/AdvancedAnalysis';

function Dashboard({ accountData }) {
  const [revenueData, setRevenueData] = useState(null);
  const [riskData, setRiskData] = useState(null);
  const [brandData, setBrandData] = useState(null);

  useEffect(() => {
    // Fetch revenue recommendation
    fetch('/api/account-analysis/revenue', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        engagement_rate: accountData.engagement_rate,
        follower_count: accountData.follower_count,
        niche: accountData.niche
      })
    }).then(res => res.json()).then(setRevenueData);

    // Fetch risk assessment
    fetch('/api/account-analysis/risks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ posts: accountData.posts })
    }).then(res => res.json()).then(setRiskData);

    // Fetch brand readiness
    fetch('/api/account-analysis/brand-readiness', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ posts: accountData.posts })
    }).then(res => res.json()).then(setBrandData);
  }, [accountData]);

  return (
    <AdvancedAnalysis
      revenueData={revenueData}
      riskData={riskData}
      brandReadinessData={brandData}
    />
  );
}
```

---

## Common Use Cases

### 1. Creator Pricing Dashboard

Show creators their recommended rates and how to increase them.

### 2. Brand Partnership Readiness

Display brand readiness score to help creators understand their market position.

### 3. Account Health Monitoring

Alert creators to declining engagement or brand safety issues.

### 4. Revenue Optimization

Help creators maximize their earnings with data-driven pricing.

---

## Next Steps

- Read the full [API Documentation](ADVANCED_ANALYSIS_API.md)
- Check out the [Frontend Components](../frontend/src/components/AdvancedAnalysis.jsx)
- Review the [Service Implementation](../backend/app/services/)
