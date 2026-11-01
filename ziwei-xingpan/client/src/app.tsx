import { Component } from 'react';
import type { PropsWithChildren } from 'react';
import './styles/index.scss';
import './styles/theme.scss';

export default class App extends Component<PropsWithChildren> {
  render() {
    return this.props.children;
  }
}
