import React from "react";

type ErrorBoundaryState = {
  error: Error | null;
};

export class ErrorBoundary extends React.Component<React.PropsWithChildren, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <main className="app-error-shell">
          <h1>窗口加载失败</h1>
          <p>{this.state.error.message || "前端运行时出现异常。"}</p>
        </main>
      );
    }

    return this.props.children;
  }
}
