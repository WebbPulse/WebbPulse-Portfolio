import { useState, useEffect, useCallback } from 'react';
import { apiService } from '../services/api';
import type {
  Project,
  Experience,
  Skill,
  Education,
  Certification,
  SiteContent,
} from '../services/api';

interface UseApiDataState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

interface UseApiDataReturn<T> extends UseApiDataState<T> {
  refetch: () => Promise<void>;
}

// Hook for fetching projects
export function useProjects(
  featuredOnly: boolean = false
): UseApiDataReturn<Project[]> {
  const [state, setState] = useState<UseApiDataState<Project[]>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchProjects = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    const response = await apiService.getProjects(featuredOnly);

    if (response.error) {
      setState({
        data: null,
        loading: false,
        error: response.error,
      });
    } else {
      setState({
        data: response.data,
        loading: false,
        error: null,
      });
    }
  }, [featuredOnly]);

  useEffect(() => {
    void fetchProjects();
  }, [fetchProjects]);

  return {
    ...state,
    refetch: fetchProjects,
  };
}

// Hook for fetching experience
export function useExperience(): UseApiDataReturn<Experience[]> {
  const [state, setState] = useState<UseApiDataState<Experience[]>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchExperience = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    const response = await apiService.getExperience();

    if (response.error) {
      setState({
        data: null,
        loading: false,
        error: response.error,
      });
    } else {
      setState({
        data: response.data,
        loading: false,
        error: null,
      });
    }
  }, []);

  useEffect(() => {
    void fetchExperience();
  }, [fetchExperience]);

  return {
    ...state,
    refetch: fetchExperience,
  };
}

// Hook for fetching a single project
export function useProject(id: number): UseApiDataReturn<Project> {
  const [state, setState] = useState<UseApiDataState<Project>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchProject = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    const response = await apiService.getProject(id);

    if (response.error) {
      setState({
        data: null,
        loading: false,
        error: response.error,
      });
    } else {
      setState({
        data: response.data,
        loading: false,
        error: null,
      });
    }
  }, [id]);

  useEffect(() => {
    if (id) {
      void fetchProject();
    }
  }, [fetchProject, id]);

  return {
    ...state,
    refetch: fetchProject,
  };
}

// Hook for fetching skills
export function useSkills(): UseApiDataReturn<Skill[]> {
  const [state, setState] = useState<UseApiDataState<Skill[]>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchSkills = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    const response = await apiService.getSkills();
    if (response.error) {
      setState({ data: null, loading: false, error: response.error });
    } else {
      setState({ data: response.data, loading: false, error: null });
    }
  }, []);

  useEffect(() => {
    void fetchSkills();
  }, [fetchSkills]);

  return { ...state, refetch: fetchSkills };
}

// Hook for fetching education
export function useEducation(): UseApiDataReturn<Education[]> {
  const [state, setState] = useState<UseApiDataState<Education[]>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchEducation = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    const response = await apiService.getEducation();
    if (response.error) {
      setState({ data: null, loading: false, error: response.error });
    } else {
      setState({ data: response.data, loading: false, error: null });
    }
  }, []);

  useEffect(() => {
    void fetchEducation();
  }, [fetchEducation]);

  return { ...state, refetch: fetchEducation };
}

// Hook for fetching certifications
export function useCertifications(): UseApiDataReturn<Certification[]> {
  const [state, setState] = useState<UseApiDataState<Certification[]>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchCerts = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    const response = await apiService.getCertifications();
    if (response.error) {
      setState({ data: null, loading: false, error: response.error });
    } else {
      setState({ data: response.data, loading: false, error: null });
    }
  }, []);

  useEffect(() => {
    void fetchCerts();
  }, [fetchCerts]);

  return { ...state, refetch: fetchCerts };
}

// Hook for fetching site content (singleton)
export function useSiteContent(): UseApiDataReturn<SiteContent> {
  const [state, setState] = useState<UseApiDataState<SiteContent>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchSiteContent = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));
    const response = await apiService.getSiteContent();
    if (response.error) {
      setState({ data: null, loading: false, error: response.error });
    } else {
      setState({ data: response.data, loading: false, error: null });
    }
  }, []);

  useEffect(() => {
    void fetchSiteContent();
  }, [fetchSiteContent]);

  return { ...state, refetch: fetchSiteContent };
}

// Hook for fetching a single experience entry
export function useExperienceEntry(id: number): UseApiDataReturn<Experience> {
  const [state, setState] = useState<UseApiDataState<Experience>>({
    data: null,
    loading: true,
    error: null,
  });

  const fetchExperienceEntry = useCallback(async () => {
    setState(prev => ({ ...prev, loading: true, error: null }));

    const response = await apiService.getExperienceEntry(id);

    if (response.error) {
      setState({
        data: null,
        loading: false,
        error: response.error,
      });
    } else {
      setState({
        data: response.data,
        loading: false,
        error: null,
      });
    }
  }, [id]);

  useEffect(() => {
    if (id) {
      void fetchExperienceEntry();
    }
  }, [fetchExperienceEntry, id]);

  return {
    ...state,
    refetch: fetchExperienceEntry,
  };
}
