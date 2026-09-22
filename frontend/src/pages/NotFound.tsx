import { Link } from 'react-router-dom';
import { Ghost } from 'lucide-react';
import { Button, EmptyState } from '../components/ui';

export default function NotFound() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <EmptyState
        icon={Ghost}
        title="Page not found"
        message="The page you're looking for doesn't exist or was moved."
        action={
          <Link to="/dashboard">
            <Button>Back to dashboard</Button>
          </Link>
        }
      />
    </div>
  );
}
