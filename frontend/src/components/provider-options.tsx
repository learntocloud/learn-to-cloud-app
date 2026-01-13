"use client";

import { useState } from "react";
import type { ProviderOption } from "@/lib/types";

interface ProviderOptionsProps {
  options: ProviderOption[];
}

const providerLabels: Record<string, { name: string; icon: string; color: string }> = {
  aws: { 
    name: "AWS", 
    icon: "☁️",
    color: "bg-orange-100 dark:bg-orange-900/30 text-orange-700 dark:text-orange-300 border-orange-200 dark:border-orange-800"
  },
  azure: { 
    name: "Azure", 
    icon: "☁️",
    color: "bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border-blue-200 dark:border-blue-800"
  },
  gcp: { 
    name: "GCP", 
    icon: "☁️",
    color: "bg-red-100 dark:bg-red-900/30 text-red-700 dark:text-red-300 border-red-200 dark:border-red-800"
  },
};

export function ProviderOptions({ options }: ProviderOptionsProps) {
  const [selectedProvider, setSelectedProvider] = useState<string>(options[0]?.provider || "aws");
  
  const selectedOption = options.find(o => o.provider === selectedProvider);

  return (
    <div className="mt-3 border border-gray-200 dark:border-gray-700 rounded-lg overflow-hidden">
      {/* Tab buttons */}
      <div className="flex border-b border-gray-200 dark:border-gray-700 bg-gray-50 dark:bg-gray-800/50">
        {options.map((option) => {
          const provider = providerLabels[option.provider] || { name: option.provider, icon: "☁️", color: "" };
          const isSelected = selectedProvider === option.provider;
          
          return (
            <button
              key={option.provider}
              onClick={() => setSelectedProvider(option.provider)}
              className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                isSelected
                  ? "bg-white dark:bg-gray-800 text-gray-900 dark:text-white border-b-2 border-blue-500 -mb-px"
                  : "text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700/50"
              }`}
            >
              {provider.name}
            </button>
          );
        })}
      </div>
      
      {/* Selected option content */}
      {selectedOption && (
        <div className="p-4 bg-white dark:bg-gray-800">
          <a
            href={selectedOption.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300 hover:underline font-medium"
          >
            {selectedOption.title}
            <svg className="w-4 h-4 inline-block ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
            </svg>
          </a>
          {selectedOption.description && (
            <p className="mt-2 text-sm text-gray-600 dark:text-gray-400">
              {selectedOption.description}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
