import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & {
  size?: number | string;
  strokeWidth?: number | string;
};

function icon(paths: ReactNode) {
  return function EasyDesignIcon({
    size = 20,
    strokeWidth = 2,
    ...props
  }: IconProps) {
    return (
      <svg
        aria-hidden="true"
        fill="none"
        height={size}
        viewBox="0 0 24 24"
        width={size}
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={strokeWidth}
        {...props}
      >
        {paths}
      </svg>
    );
  };
}

export const Box = icon(<><path d="m4 7 8-4 8 4-8 4-8-4Z" /><path d="M4 7v10l8 4 8-4V7M12 11v10" /></>);
export const ChevronDown = icon(<path d="m6 9 6 6 6-6" />);
export const Download = icon(<><path d="M12 3v12m-4-4 4 4 4-4" /><path d="M5 21h14" /></>);
export const Eye = icon(<><path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" /><circle cx="12" cy="12" r="2.5" /></>);
export const EyeOff = icon(<><path d="m3 3 18 18" /><path d="M10.6 6.2A11 11 0 0 1 12 6c6.5 0 10 6 10 6a16 16 0 0 1-3 3.8M6.5 6.5C3.5 8.3 2 12 2 12s3.5 6 10 6a10 10 0 0 0 3-.4" /></>);
export const FileBox = icon(<><path d="M6 2h8l4 4v16H6z" /><path d="M14 2v5h5" /><rect x="9" y="12" width="6" height="5" rx="1" /></>);
export const FileCode2 = icon(<><path d="M6 2h8l4 4v16H6z" /><path d="M14 2v5h5M10 12l-2 2 2 2m4-4 2 2-2 2" /></>);
export const Focus = icon(<path d="M8 3H3v5m13-5h5v5M8 21H3v-5m13 5h5v-5M9 12h6" />);
export const ImageDown = icon(<><rect x="3" y="3" width="18" height="14" rx="2" /><path d="m3 14 5-5 4 4 2-2 4 4M12 18v4m-2-2 2 2 2-2" /></>);
export const ListTree = icon(<path d="M3 5h4m-4 7h4m-4 7h4M7 5v14m0-7h5m0-5h9m-9 5h9m-9 7h9" />);
export const LoaderCircle = icon(<><path d="M21 12a9 9 0 1 1-6.2-8.6" /><path d="M21 3v6h-6" /></>);
export const MousePointer2 = icon(<path d="m4 3 7 17 2.2-6.8L20 11 4 3Z" />);
export const Palette = icon(<><path d="M12 3a9 9 0 0 0 0 18h1.5a2 2 0 0 0 0-4H12a2 2 0 0 1 0-4h4a5 5 0 0 0 0-10Z" /><circle cx="7.5" cy="10" r=".5" /><circle cx="9.5" cy="6.5" r=".5" /></>);
export const Play = icon(<path d="m8 5 11 7-11 7Z" />);
export const Redo2 = icon(<path d="m17 7 4 4-4 4M3 17v-2a4 4 0 0 1 4-4h14" />);
export const RefreshCw = icon(<><path d="M20 7v5h-5M4 17v-5h5" /><path d="M6 8a7 7 0 0 1 12-2l2 1M18 16a7 7 0 0 1-12 2l-2-1" /></>);
export const Tag = icon(<path d="M3 12V4h8l10 10-7 7L3 12Zm5-4h.01" />);
export const TerminalSquare = icon(<><rect x="3" y="3" width="18" height="18" rx="2" /><path d="m7 9 3 3-3 3m5 0h5" /></>);
export const TriangleAlert = icon(<><path d="m12 3 10 18H2L12 3Z" /><path d="M12 9v5m0 3h.01" /></>);
export const Undo2 = icon(<path d="m7 7-4 4 4 4m14 2v-2a4 4 0 0 0-4-4H3" />);
export const X = icon(<path d="M5 5l14 14M19 5 5 19" />);
