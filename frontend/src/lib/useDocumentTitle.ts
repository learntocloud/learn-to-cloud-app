import { useEffect } from 'react';

/**
 * Set the document title. Resets to default on unmount if resetOnUnmount is true.
 */
export function useDocumentTitle(title: string, resetOnUnmount = false): void {
  useEffect(() => {
    const previousTitle = document.title;
    document.title = title;

    return () => {
      if (resetOnUnmount) {
        document.title = previousTitle;
      }
    };
  }, [title, resetOnUnmount]);
}
