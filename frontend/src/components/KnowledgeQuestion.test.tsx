import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { KnowledgeQuestion } from './KnowledgeQuestion';
import { QUESTION_ANSWER_MAX_CHARS, QUESTION_ANSWER_MIN_CHARS } from '@/lib/constants';

describe('KnowledgeQuestion', () => {
  const mockQuestion = {
    id: 'q1',
    prompt: 'What is cloud computing?',
    expected_concepts: ['scalability', 'on-demand'],
  };

  type SubmitResult = { is_passed: boolean; llm_feedback?: string | null };
  let mockOnSubmit: ReturnType<typeof vi.fn<[string], Promise<SubmitResult>>>;

  beforeEach(() => {
    mockOnSubmit = vi.fn<[string], Promise<SubmitResult>>();
  });

  describe('rendering', () => {
    it('renders question prompt', () => {
      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.getByText('What is cloud computing?')).toBeInTheDocument();
    });

    it('shows passed state when isAnswered is true', () => {
      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={true}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.getByText("You've passed this question")).toBeInTheDocument();
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument();
    });

    it('shows textarea and submit button when not answered', () => {
      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.getByPlaceholderText('Type your answer here...')).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /submit answer/i })).toBeInTheDocument();
    });
  });

  describe('validation', () => {
    it('disables submit button when answer is too short', () => {
      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      fireEvent.change(textarea, { target: { value: 'Short' } });

      expect(submitButton).toBeDisabled();
    });

    it('shows error when submitting answer below minimum length', async () => {
      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      fireEvent.change(textarea, { target: { value: 'Short' } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(
          screen.getByText(`Answer must be at least ${QUESTION_ANSWER_MIN_CHARS} characters.`)
        ).toBeInTheDocument();
      });

      expect(mockOnSubmit).not.toHaveBeenCalled();
    });

    it('shows character count', () => {
      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      expect(screen.getByText(`0/${QUESTION_ANSWER_MAX_CHARS}`)).toBeInTheDocument();
    });

    it('updates character count as user types', async () => {
      const user = userEvent.setup();
      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      await user.type(textarea, 'Cloud computing is...');

      expect(screen.getByText(`21/${QUESTION_ANSWER_MAX_CHARS}`)).toBeInTheDocument();
    });

    it('shows warning when over character limit', async () => {
      const user = userEvent.setup();
      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      const longText = 'a'.repeat(QUESTION_ANSWER_MAX_CHARS + 1);
      await user.type(textarea, longText);

      const charCount = screen.getByText(new RegExp(`${QUESTION_ANSWER_MAX_CHARS + 1}/${QUESTION_ANSWER_MAX_CHARS}`));
      expect(charCount).toHaveClass('text-red-500');
    });
  });

  describe('submission', () => {
    it('submits answer when valid', async () => {
      mockOnSubmit.mockResolvedValue({
        is_passed: true,
        llm_feedback: 'Great answer!',
      });

      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      const validAnswer = 'Cloud computing is a model for enabling ubiquitous access to shared resources.';
      fireEvent.change(textarea, { target: { value: validAnswer } });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(mockOnSubmit).toHaveBeenCalledWith(validAnswer);
      });
    });

    it('shows loading state while submitting', async () => {
      mockOnSubmit.mockImplementation(
        () => new Promise(resolve => setTimeout(() => resolve({ is_passed: true }), 100))
      );

      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      fireEvent.change(textarea, {
        target: { value: 'Valid answer with enough characters to pass validation.' },
      });
      fireEvent.click(submitButton);

      expect(await screen.findByText('Checking...')).toBeInTheDocument();
    });

    it('shows success feedback when answer passes', async () => {
      mockOnSubmit.mockResolvedValue({
        is_passed: true,
        llm_feedback: 'Excellent understanding!',
      });

      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      fireEvent.change(textarea, {
        target: { value: 'Valid answer with enough characters to pass.' },
      });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText('Excellent understanding!')).toBeInTheDocument();
      });
    });

    it('shows failure feedback when answer does not pass', async () => {
      mockOnSubmit.mockResolvedValue({
        is_passed: false,
        llm_feedback: 'Please include more detail about scalability.',
      });

      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      fireEvent.change(textarea, {
        target: { value: 'Incomplete answer without key concepts.' },
      });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText(/Please include more detail about scalability/)).toBeInTheDocument();
      });
    });

    it('handles submission errors gracefully', async () => {
      mockOnSubmit.mockRejectedValue(new Error('Network error'));

      render(
        <KnowledgeQuestion
          question={mockQuestion}
          isAnswered={false}
          onSubmit={mockOnSubmit}
        />
      );

      const textarea = screen.getByPlaceholderText('Type your answer here...');
      const submitButton = screen.getByRole('button', { name: /submit answer/i });

      fireEvent.change(textarea, {
        target: { value: 'Valid answer with enough characters.' },
      });
      fireEvent.click(submitButton);

      await waitFor(() => {
        expect(screen.getByText('Failed to submit your answer. Please try again.')).toBeInTheDocument();
      });
    });
  });
});
