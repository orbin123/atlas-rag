import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SafeAnswer } from './DashboardChat';

describe('SafeAnswer', () => {
  it('renders document and model text as escaped text while styling citation labels', () => {
    const html = renderToStaticMarkup(<SafeAnswer text={'<img src=x onerror=alert(1)> [S1]'} />);
    expect(html).toContain('&lt;img src=x onerror=alert(1)&gt;');
    expect(html).not.toContain('<img');
    expect(html).toContain('[S1]');
  });
});
