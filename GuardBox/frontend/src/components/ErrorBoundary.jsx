import React from 'react';

export default class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('[GuardBox ErrorBoundary] Uncaught component exception:', error, errorInfo);
    this.setState({ errorInfo });
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          minHeight: '100vh',
          backgroundColor: '#070B10',
          color: '#F8FAFC',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '24px',
          fontFamily: 'system-ui, -apple-system, sans-serif'
        }}>
          <div style={{
            maxWidth: '480px',
            width: '100%',
            backgroundColor: '#0D141F',
            border: '1px solid #1E2A39',
            borderRadius: '12px',
            padding: '32px',
            textAlign: 'center',
            boxShadow: '0 8px 32px rgba(0,0,0,0.5)'
          }}>
            <h1 style={{
              fontSize: '24px',
              fontWeight: 700,
              letterSpacing: '0.05em',
              color: '#8FC7F2',
              marginBottom: '8px'
            }}>
              TRINETRA
            </h1>
            <p style={{
              fontSize: '16px',
              color: '#9DB4C6',
              marginBottom: '24px'
            }}>
              Something went wrong.
            </p>
            {this.state.error && (
              <div style={{
                backgroundColor: '#04070A',
                border: '1px solid #1E2A39',
                borderRadius: '6px',
                padding: '12px',
                marginBottom: '24px',
                textAlign: 'left',
                fontFamily: 'monospace',
                fontSize: '12px',
                color: '#EF4444',
                overflowX: 'auto',
                maxHeight: '150px'
              }}>
                {this.state.error.toString()}
              </div>
            )}
            <button
              onClick={this.handleReload}
              style={{
                backgroundColor: '#2563EB',
                color: '#FFFFFF',
                border: 'none',
                borderRadius: '6px',
                padding: '10px 24px',
                fontSize: '14px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'background-color 0.2s'
              }}
              onMouseOver={(e) => e.currentTarget.style.backgroundColor = '#1D4ED8'}
              onMouseOut={(e) => e.currentTarget.style.backgroundColor = '#2563EB'}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}
