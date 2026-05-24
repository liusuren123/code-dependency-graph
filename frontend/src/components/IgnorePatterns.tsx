import React, { useState, useRef } from 'react';
import { X, RotateCcw } from 'lucide-react';
import styles from './IgnorePatterns.module.css';

interface IgnorePatternsProps {
  patterns: string[];
  onChange: (patterns: string[]) => void;
  defaults: string[];
}

export const IgnorePatterns: React.FC<IgnorePatternsProps> = ({ patterns, onChange, defaults }) => {
  const [input, setInput] = useState('');
  const inputRef = useRef<HTMLInputElement>(null);

  const addPattern = () => {
    const val = input.trim();
    if (!val || patterns.includes(val)) return;
    onChange([...patterns, val]);
    setInput('');
    inputRef.current?.focus();
  };

  const removePattern = (p: string) => {
    onChange(patterns.filter(x => x !== p));
  };

  const resetDefaults = () => {
    onChange([...defaults]);
  };

  return (
    <div className={styles.container}>
      <div className={styles.tagList}>
        {patterns.map(p => (
          <span key={p} className={styles.tag}>
            {p}
            <button className={styles.tagRemove} onClick={() => removePattern(p)}>
              <X size={12} />
            </button>
          </span>
        ))}
      </div>
      <div className={styles.inputRow}>
        <input
          ref={inputRef}
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); addPattern(); } }}
          placeholder="Add pattern, Enter to confirm"
          className={styles.input}
        />
        <button className={styles.addBtn} onClick={addPattern}>Add</button>
      </div>
      <button className={styles.resetBtn} onClick={resetDefaults}>
        <RotateCcw size={12} /> Reset Defaults
      </button>
    </div>
  );
};
