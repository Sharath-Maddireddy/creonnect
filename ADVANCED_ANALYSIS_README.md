# Advanced Account Analysis

A comprehensive set of tools for creator monetization optimization, risk monitoring, and brand partnership readiness assessment.

## Features

### 1. Revenue Optimization Calculator

Dynamic rate recommendations based on:
- Engagement rate
- Follower count
- Niche market multipliers
- Content quality scores
- Brand safety scores

**Endpoint:** `POST /api/account-analysis/revenue`

### 2. Risk Assessment Dashboard

Proactive monitoring for:
- Engagement rate declines
- Brand safety issues
- Posting frequency problems
- Content quality concerns
- Growth slowdowns

**Endpoint:** `POST /api/account-analysis/risks`

### 3. Brand Readiness Scoring

Detailed component scores for:
- Content quality
- Brand safety
- Engagement rate
- Posting consistency
- Niche clarity
- Audience quality

**Endpoint:** `POST /api/account-analysis/brand-readiness`

---

## Installation

The advanced analysis features are included in the main creonnect backend. No additional installation required.

### Dependencies

- Python 3.10+
- FastAPI
- Pydantic

---

## Quick Start

### 1. Start the Server

```bash
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### 2. Test the Endpoints

```bash
# Revenue Calculator
curl -X POST http://localhost:8000/api/account-analysis/revenue \
  -H "Content-Type: application/json" \
  -d '{"engagement_rate": 0.05, "follower_count": 50000, "niche": "fashion"}'

# Risk Assessment
curl -X POST http://localhost:8000/api/account-analysis/risks \
  -H "Content-Type: application/json" \
  -d '{"posts": []}'

# Brand Readiness
curl -X POST http://localhost:8000/api/account-analysis/brand-readiness \
  -H "Content-Type: application/json" \
  -d '{"posts": []}'
```

---

## API Documentation

See [ADVANCED_ANALYSIS_API.md](docs/ADVANCED_ANALYSIS_API.md) for complete API documentation.

---

## Frontend Integration

Import the React components:

```jsx
import AdvancedAnalysis from './components/AdvancedAnalysis';

function Dashboard({ data }) {
  return (
    <AdvancedAnalysis
      revenueData={data.revenue}
      riskData={data.risks}
      brandReadinessData={data.brandReadiness}
    />
  );
}
```

---

## Architecture

### Services

| Service | File | Purpose |
|---------|------|---------|
| Revenue Calculator | `backend/app/services/revenue_calculator.py` | Rate recommendations |
| Risk Assessment | `backend/app/services/risk_assessment.py` | Risk detection |
| Brand Readiness | `backend/app/services/brand_readiness.py` | Brand scoring |

### API Routes

| Route | File | Purpose |
|-------|------|---------|
| Advanced Analysis | `backend/app/api/advanced_analysis_routes.py` | API endpoints |

### Domain Models

| Model | File | Purpose |
|-------|------|---------|
| RateRecommendation | `backend/app/domain/account_models.py` | Revenue data |
| RiskAssessment | `backend/app/domain/account_models.py` | Risk data |
| BrandReadinessBreakdown | `backend/app/domain/account_models.py` | Brand data |

---

## Testing

Run the test suite:

```bash
pytest backend/app/tests/test_advanced_analysis.py -v
```

All 16 tests should pass.

---

## Configuration

### Niche Multipliers

Customize niche multipliers in `revenue_calculator.py`:

```python
NICHE_MULTIPLIERS = {
    "fashion": 1.20,
    "beauty": 1.15,
    "tech": 1.10,
    # Add more niches as needed
}
```

### Risk Thresholds

Customize risk detection thresholds in `risk_assessment.py`:

```python
RISK_RULES = {
    "engagement_decline": {
        "threshold": -0.15,  # 15% decline triggers risk
        "level": RiskLevel.MEDIUM,
    },
    # Adjust thresholds as needed
}
```

---

## Performance

| Endpoint | Response Time (p95) | Payload Size |
|----------|---------------------|--------------|
| `/revenue` | <200ms | <5KB |
| `/risks` | <300ms | <10KB |
| `/brand-readiness` | <250ms | <8KB |

---

## Security

- All inputs validated via Pydantic models
- Rate limiting applied to all endpoints
- No sensitive data stored or logged

---

## Changelog

### v1.0.0 (2025-07-23)

- Initial release
- Revenue Calculator
- Risk Assessment
- Brand Readiness

---

## License

Internal use only - Creonnect Platform

---

## Support

For issues or questions, contact the engineering team.
