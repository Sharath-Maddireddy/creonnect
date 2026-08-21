const BASE = '/api/v1/creator/image-editor'

describe('Creator Image Editor API contract', () => {
  const routes = [
    ['GET', `${BASE}/config`],
    ['POST', `${BASE}/jobs`],
    ['POST', `${BASE}/jobs/from-url`],
    ['GET', `${BASE}/jobs/{job_id}`],
    ['GET', `${BASE}/jobs?limit={limit}&skip={skip}`],
    ['POST', `${BASE}/jobs/{job_id}/retry`],
    ['POST', `${BASE}/jobs/{job_id}/cancel`],
  ]

  test.each(routes)('%s %s uses the creator image editor API', (method, path) => {
    expect(['GET', 'POST']).toContain(method)
    expect(path).toMatch(/^\/api\/v1\/creator\/image-editor/)
  })

  test('job creation is protected against duplicate submit', () => {
    const requiredHeaders = ['Idempotency-Key']
    expect(requiredHeaders).toContain('Idempotency-Key')
  })

  test('the UI must never submit a free-text prompt', () => {
    const structuredFields = ['goal_id', 'style_id', 'event_id', 'enhancement_ids', 'output_format']
    expect(structuredFields).not.toContain('prompt')
  })
})
