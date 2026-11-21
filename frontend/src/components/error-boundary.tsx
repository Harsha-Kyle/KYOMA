import { Component, ErrorInfo, ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[Uncaught Frontend Error]:", error, errorInfo);
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div style={{
          backgroundColor: "#030712",
          color: "#f87171",
          fontFamily: "monospace",
          padding: "32px",
          height: "100vh",
          overflow: "auto"
        }}>
          <h2 style={{ fontSize: "20px", fontWeight: "bold", marginBottom: "12px" }}>
            [Kyoma Frontend Runtime Error]
          </h2>
          <pre style={{ backgroundColor: "#111827", padding: "16px", borderRadius: "8px", whiteSpace: "pre-wrap" }}>
            {this.state.error?.stack || this.state.error?.message || String(this.state.error)}
          </pre>
          <button
            onClick={() => window.location.reload()}
            style={{
              marginTop: "16px",
              padding: "8px 16px",
              backgroundColor: "#1f2937",
              color: "#e5e7eb",
              border: "1px solid #374151",
              borderRadius: "4px",
              cursor: "pointer"
            }}
          >
            Reload UI
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
