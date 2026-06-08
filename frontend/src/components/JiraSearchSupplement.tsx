import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { UserCircle2 } from 'lucide-react';

export interface JiraSearchSupplementCard {
  id: string;
  prompt: string;
  choices: { value: string; label: string }[];
  /** intent = 路由消歧；默认 jira 用户补全 */
  kind?: 'jira_user' | 'intent';
}

interface Props {
  card: JiraSearchSupplementCard;
  onSelect: (username: string) => void;
  onDismiss: () => void;
}

export default function JiraSearchSupplement({ card, onSelect, onDismiss }: Props) {
  const [selected, setSelected] = useState('');

  return (
    <div className="mt-3 border border-blue-400/50 bg-blue-50/30 dark:bg-blue-950/20 rounded-lg p-4">
      <div className="flex items-start gap-2 mb-3">
        <UserCircle2 className="w-5 h-5 text-blue-500 shrink-0" />
        <p className="text-sm text-blue-800 dark:text-blue-200">{card.prompt}</p>
      </div>
      <div className="flex flex-wrap gap-2 mb-3">
        {card.choices.map((c) => (
          <Button
            key={c.value}
            size="sm"
            variant={selected === c.value ? 'default' : 'outline'}
            onClick={() => setSelected(c.value)}
          >
            {c.label || c.value}
          </Button>
        ))}
      </div>
      <div className="flex gap-2 justify-end">
        <Button size="sm" variant="ghost" onClick={onDismiss}>
          跳过
        </Button>
        <Button
          size="sm"
          disabled={!selected}
          onClick={() => selected && onSelect(selected)}
        >
          {card.kind === 'intent' ? '按此意图继续' : '确认用户并继续查询'}
        </Button>
      </div>
    </div>
  );
}
