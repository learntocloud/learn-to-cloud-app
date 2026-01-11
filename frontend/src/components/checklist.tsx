"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { ChecklistItemWithProgress } from "@/lib/types";
import { useApi } from "@/lib/use-api";

interface ChecklistProps {
  items: ChecklistItemWithProgress[];
}

export function Checklist({ items }: ChecklistProps) {
  return (
    <div className="space-y-2">
      {items.map((item) => (
        <ChecklistItem key={item.id} item={item} />
      ))}
    </div>
  );
}

function ChecklistItem({ item }: { item: ChecklistItemWithProgress }) {
  const router = useRouter();
  const api = useApi();
  const [isCompleted, setIsCompleted] = useState(item.is_completed);
  const [isUpdating, setIsUpdating] = useState(false);

  const handleToggle = async () => {
    if (isUpdating) return;
    setIsUpdating(true);
    
    try {
      const result = await api.toggleChecklistItem(item.id);
      setIsCompleted(result.is_completed);
      router.refresh();
    } catch (error) {
      console.error("Failed to toggle checklist item:", error);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <label className="flex items-start gap-3 p-3 bg-gray-50 dark:bg-gray-700 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-600 cursor-pointer transition-colors">
      <input
        type="checkbox"
        checked={isCompleted}
        onChange={handleToggle}
        disabled={isUpdating}
        className="mt-0.5 h-4 w-4 text-green-600 rounded border-gray-300 dark:border-gray-500 focus:ring-green-500 disabled:opacity-50"
      />
      <span className={`text-sm ${isCompleted ? "text-gray-500 dark:text-gray-400 line-through" : "text-gray-700 dark:text-gray-300"}`}>
        {item.text}
      </span>
    </label>
  );
}
