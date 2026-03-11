import { createContext, useContext, ReactNode } from "react";

interface DesktopUser {
  id: string;
  email: string;
  name: string;
  role: string;
  organization: string;
}

interface AuthContextType {
  user: DesktopUser;
  loading: boolean;
  isAuthenticated: boolean;
  signOut: () => Promise<void>;
}

const DESKTOP_USER: DesktopUser = {
  id: "local-user",
  email: "user@desktop.local",
  name: "Solo User",
  role: "admin",
  organization: "local",
};

const AuthContext = createContext<AuthContextType>({
  user: DESKTOP_USER,
  loading: false,
  isAuthenticated: true,
  signOut: async () => {},
});

export function DesktopAuthProvider({ children }: { children: ReactNode }) {
  return (
    <AuthContext.Provider value={{
      user: DESKTOP_USER,
      loading: false,
      isAuthenticated: true,
      signOut: async () => { /* In desktop mode, "sign out" could quit the app */ },
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
