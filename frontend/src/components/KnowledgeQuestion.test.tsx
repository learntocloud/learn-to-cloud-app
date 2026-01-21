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

describe('KnowledgeQuestion', () => {
  const mockOnSubmit = vi.fn();

  beforeEach(() => {
    mockOnSubmit.mockReset();
    mockOnSubmit.mockResolvedValue({
      is_passed: false,
      llm_feedback: 'Please provide more detail about scalability.',
      attempts_used: 1,
    });
  });

  it('renders question prompt', () => {
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    expect(screen.getByText(mockQuestion.prompt)).toBeInTheDocument();
  });

  it('renders textarea for answer input', () => {
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeInTheDocument();
    expect(textarea).toHaveAttribute('placeholder', expect.stringContaining('interview'));
  });

  it('shows submit button', () => {
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    expect(screen.getByRole('button', { name: /submit answer/i })).toBeInTheDocument();
  });

  it('disables submit for answers below minimum length', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'short');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    expect(submitButton).toBeDisabled();
  });

  it('enables submit for valid length answers', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'This is a sufficiently long answer that meets the minimum character requirement.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    expect(submitButton).toBeEnabled();
  });

  it('shows character count', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'Test answer');

    // Character count should be visible
    expect(screen.getByText(/11\/512/)).toBeInTheDocument();
  });

  it('calls onSubmit when form is submitted', async () => {
    const user = userEvent.setup();
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    const textarea = screen.getByRole('textbox');
    const answer = 'Cloud computing is the delivery of computing services over the internet.';
    await user.type(textarea, answer);

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    expect(mockOnSubmit).toHaveBeenCalledWith(answer);
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
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

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
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    const textarea = screen.getByRole('textbox');
    await user.type(textarea, 'Cloud computing is the on-demand delivery of IT resources over the internet with pay-as-you-go pricing.');

    const submitButton = screen.getByRole('button', { name: /submit answer/i });
    await user.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/passed this question/i)).toBeInTheDocument();
    });
  });

  it('shows already passed state', () => {
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={true}
        onSubmit={mockOnSubmit}
      />
    );

    expect(screen.getByText(/passed this question/i)).toBeInTheDocument();
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
  });

  it('shows loading state while submitting', async () => {
    const user = userEvent.setup();
    // Make onSubmit take some time
    mockOnSubmit.mockImplementation(() => new Promise((resolve) => setTimeout(resolve, 1000)));

    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

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
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

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
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

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
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

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

  it('disables input when locked out', () => {
    const lockoutUntil = new Date(Date.now() + 30 * 60 * 1000);

    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        initialLockoutUntil={lockoutUntil}
        initialAttemptsUsed={3}
        onSubmit={mockOnSubmit}
      />
    );

    const textarea = screen.getByRole('textbox');
    expect(textarea).toBeDisabled();
  });

  it('has accessible labels and descriptions', () => {
    render(
      <KnowledgeQuestion
        question={mockQuestion}
        isAnswered={false}
        onSubmit={mockOnSubmit}
      />
    );

    const textarea = screen.getByRole('textbox');
    // Should have aria-labelledby pointing to the question prompt
    expect(textarea).toHaveAttribute('aria-labelledby');
  });
});
