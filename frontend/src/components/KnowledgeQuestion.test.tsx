/**
 * Tests for KnowledgeQuestion component.
 * Tests answer submission, validation, feedback display, and lockout behavior.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, userEvent, waitFor } from '../test/test-utils';
import { KnowledgeQuestion } from './KnowledgeQuestion';
import { LockoutError } from '@/lib/api-client';
import type { QuestionSchema } from '@/lib/api-client';

const mockQuestion: QuestionSchema = {
  id: 'q1',
  prompt: 'What is cloud computing and why is it important?',
};

// Use vi.hoisted to create mock that's available during module mocking
const { mockGetScenarioQuestion } = vi.hoisted(() => ({
  mockGetScenarioQuestion: vi.fn(),
}));

vi.mock('@/lib/hooks', () => ({
  useApi: () => ({
    getScenarioQuestion: mockGetScenarioQuestion,
  }),
}));

describe('KnowledgeQuestion', () => {
  const mockOnSubmit = vi.fn();

  beforeEach(() => {
    mockOnSubmit.mockReset();
    mockOnSubmit.mockResolvedValue({
      is_passed: false,
      llm_feedback: 'Please provide more detail about scalability.',
      attempts_used: 1,
    });
    // Reset and setup the scenario mock before each test
    mockGetScenarioQuestion.mockReset();
    mockGetScenarioQuestion.mockResolvedValue({
      question_id: 'q1',
      scenario_prompt: 'You are advising a startup CTO. ' + mockQuestion.prompt,
      base_prompt: mockQuestion.prompt,
    });
  });

  // Helper to start the knowledge check
  async function startKnowledgeCheck(user: ReturnType<typeof userEvent.setup>) {
    const startButton = screen.getByRole('button', { name: /start knowledge check/i });
    await user.click(startButton);
    await waitFor(() => {
      expect(screen.queryByRole('button', { name: /start knowledge check/i })).not.toBeInTheDocument();
    });
  }

  it('shows start button initially', () => {
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    expect(screen.getByRole('button', { name: /start knowledge check/i })).toBeInTheDocument();
    expect(screen.getByText(/ready to test your knowledge/i)).toBeInTheDocument();
    expect(screen.queryByText(mockQuestion.prompt)).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('loads scenario after clicking start', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    expect(mockGetScenarioQuestion).toHaveBeenCalledWith('phase1-topic1', 'q1');
    expect(screen.getByRole('textbox')).toBeInTheDocument();
  });

  it('renders textarea for answer input after starting', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeInTheDocument();
    expect(textarea).toHaveAttribute('placeholder', expect.stringContaining('interview'));
  });

  it('shows submit button after starting', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    expect(screen.getByRole('button', { name: /submit answer/i })).toBeInTheDocument();
  });

  it('disables submit for answers below minimum length', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'short');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    expect(submitButton).toBeDisabled();
  });

  it('enables submit for valid length answers', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'This is a sufficiently long answer that meets the minimum character requirement.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    expect(submitButton).toBeEnabled();
  });

  it('shows character count', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'Test answer');

    // Character count should be visible
    expect(screen.getByText(/11\/2000/)).toBeInTheDocument();
  });

  it('calls onSubmit when form is submitted', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    const answer = 'Cloud computing is the delivery of computing services over the internet.';
    await user.type(textarea, answer);

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    // Should pass the scenario prompt (no longer undefined since we removed fallback)
    expect(mockOnSubmit).toHaveBeenCalledWith(
      answer,
      'You are advising a startup CTO. ' + mockQuestion.prompt
    );
  });

  it('shows feedback on incorrect answer', async () => {
    const user = userEvent.setup();
    mockOnSubmit.mockResolvedValue({
      is_passed: false,
      llm_feedback: 'Your answer needs more detail about on-demand resources.',
      attempts_used: 1,
    });

    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'Cloud computing is using computers on the internet.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/on-demand resources/i)).toBeInTheDocument();
    });
  });

  it('shows success state on correct answer', async () => {
    const user = userEvent.setup();
    mockOnSubmit.mockResolvedValue({
      is_passed: true,
      llm_feedback: 'Excellent answer! You demonstrated clear understanding.',
      attempts_used: null,
    });

    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'Cloud computing is the on-demand delivery of IT resources over the internet with pay-as-you-go pricing.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/passed this question/i)).toBeInTheDocument();
    });
  });

  it('shows already passed state without start button', () => {
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={true}
        onSubmit={mockOnSubmit}
      />
    );

    expect(screen.getByText(/passed this question/i)).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /start knowledge check/i })).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('shows loading state while submitting', async () => {
    const user = userEvent.setup();
    // Make onSubmit take some time
    mockOnSubmit.mockImplementation(() => new Promise((resolve) => setTimeout(resolve, 1000)));

    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'A valid answer that meets the minimum length requirement.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    // Should show loading state
    expect(screen.getByText(/checking/i)).toBeInTheDocument();
  });

  it('shows attempts used counter', async () => {
    const user = userEvent.setup();
    mockOnSubmit.mockResolvedValue({
      is_passed: false,
      llm_feedback: 'Try again with more detail.',
      attempts_used: 2,
    });

    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'An answer that needs improvement but is long enough.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/2\/3 attempts used/i)).toBeInTheDocument();
    });
  });

  it('shows lockout message when locked out', async () => {
    const user = userEvent.setup();
    const lockoutUntil = new Date(Date.now() + 30 * 60 * 1000); // 30 minutes from now
    mockOnSubmit.mockRejectedValue(
      new LockoutError('Too many attempts', lockoutUntil.toISOString(), 3, 1800)
    );

    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'Another attempt that will fail due to lockout.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/available in/i)).toBeInTheDocument();
    });
  });

  it('shows lockout banner immediately on 3rd failed attempt from response', async () => {
    const user = userEvent.setup();
    const lockoutUntil = new Date(Date.now() + 60 * 60 * 1000); // 1 hour from now
    // Simulate 3rd failed attempt where API returns lockout_until in the response
    mockOnSubmit.mockResolvedValue({
      is_passed: false,
      llm_feedback: 'Wrong answer.',
      attempts_used: 3,
      lockout_until: lockoutUntil.toISOString(),
    });

    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'Third attempt that will trigger lockout from response.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    // Should show lockout banner immediately, not the yellow feedback
    await waitFor(() => {
      expect(screen.getByText(/available in/i)).toBeInTheDocument();
    });
    // Should NOT show feedback when locked out
    expect(screen.queryByText(/wrong answer/i)).not.toBeInTheDocument();
  });

  it('shows lockout state without start button or textarea', async () => {
    const lockoutUntil = new Date(Date.now() + 30 * 60 * 1000);

    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        initialLockoutUntil={lockoutUntil}
        initialAttemptsUsed={3}
        onSubmit={mockOnSubmit}
      />
    );

    // When initially locked out, should show lockout state, not start button
    await waitFor(() => {
      expect(screen.getByText(/available in/i)).toBeInTheDocument();
    });

    expect(screen.queryByRole('button', { name: /start knowledge check/i })).not.toBeInTheDocument();
    // Question text and textarea should not be shown
    expect(screen.queryByText(mockQuestion.prompt)).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('has accessible labels and descriptions after starting', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        topicId="phase1-topic1"
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    await startKnowledgeCheck(user);

    const textarea = screen.getByRole('textbox');
    // Should have aria-labelledby pointing to the question prompt
    expect(textarea).toHaveAttribute('aria-labelledby');
  });
});
