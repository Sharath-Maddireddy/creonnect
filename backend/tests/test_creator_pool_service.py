from unittest.mock import MagicMock, patch
import pytest

from backend.app.services.creator_pool_service import (
    query_creator_pool,
    find_lookalikes,
    LookalikeEmbeddingError,
    _normalize_embedding
)
from backend.app.infra.models import CreatorDiscoveryMeta, CreatorVector

def mock_creator_row(account_id, username, followers, category, vector_embedding=None):
    meta = MagicMock(spec=CreatorDiscoveryMeta)
    meta.account_id = account_id
    meta.username = username
    meta.follower_count = followers
    meta.creator_dominant_category = category
    meta.ahs_score = 80
    meta.predicted_engagement_rate = 0.05
    meta.avg_visual_quality_score = 40.0
    meta.avg_brand_safety_score = 48.0
    meta.adult_content_detected = False
    meta.bio = "Mock bio"
    meta.avg_views = 1000
    meta.avg_likes = 100
    meta.avg_comments = 10
    meta.posts_per_week = 3.5
    meta.niche_tags = ["mock"]

    vector = None
    if vector_embedding is not None:
        vector = MagicMock(spec=CreatorVector)
        vector.embedding = vector_embedding

    return (meta, vector)

@patch('backend.app.services.creator_pool_service.get_sync_sessionmaker')
def test_query_creator_pool(mock_get_sessionmaker):
    mock_session = MagicMock()
    mock_get_sessionmaker.return_value = MagicMock(return_value=mock_session)
    mock_session.__enter__.return_value = mock_session

    # Mock the database response for session.execute(...).all()
    mock_session.execute.return_value.all.return_value = [
        mock_creator_row("1", "fit_guru", 150000, "fitness"),
        mock_creator_row("2", "foodie", 80000, "food")
    ]

    results = query_creator_pool(niche="fitness", min_followers=100000)
    
    # Check session was called
    assert mock_session.execute.called
    
    # Check that our mocked results were transformed to dictionaries properly
    assert len(results) == 2
    assert results[0]["username"] == "fit_guru"
    assert results[1]["follower_count"] == 80000

@patch('backend.app.services.creator_pool_service.get_sync_sessionmaker')
def test_find_lookalikes_pgvector(mock_get_sessionmaker):
    """Test find_lookalikes when pgvector is enabled (postgresql dialect)."""
    mock_session = MagicMock()
    mock_get_sessionmaker.return_value = MagicMock(return_value=mock_session)
    mock_session.__enter__.return_value = mock_session
    mock_session.bind.dialect.name = "postgresql"

    # target_exists check
    mock_session.scalar.side_effect = [
        "target_id", # Target exists
        [0.1, 0.2, 0.3] # Target embedding exists
    ]
    
    # The actual vector search result
    mock_row = MagicMock()
    mock_row.account_id = "lookalike_id"
    mock_session.execute.return_value.__iter__.return_value = [mock_row]
    
    # We also mock _get_creators_by_ids to just return the data instead of querying again
    with patch('backend.app.services.creator_pool_service._get_creators_by_ids') as mock_get_by_ids:
        mock_get_by_ids.return_value = [{"account_id": "lookalike_id", "username": "clone"}]
        
        results = find_lookalikes("target_id", k=1)
        
        assert results is not None
        assert len(results) == 1
        assert results[0]["username"] == "clone"
        mock_get_by_ids.assert_called_once_with(["lookalike_id"])

def test_normalize_embedding():
    # Numpy array compatibility check (simulate pgvector numpy output)
    import numpy as np
    np_arr = np.array([0.1, 0.2, 0.3])
    
    normalized = _normalize_embedding(np_arr)
    assert isinstance(normalized, list)
    assert len(normalized) == 3
    assert normalized[0] == 0.1
    
    # List compatibility
    assert _normalize_embedding([1, 2, 3]) == [1.0, 2.0, 3.0]
    
    # None handling
    assert _normalize_embedding(None) is None
